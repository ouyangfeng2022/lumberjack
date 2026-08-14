from __future__ import annotations

import pytest

from lumberjack import Lumberjack, Tree
from lumberjack.finalizer import ChunkFinalizer
from lumberjack.models import ChunkDraft, DocTree, Entry, SectionNode
from lumberjack.normalizer import TextNormalizer
from lumberjack.parser import MarkdownParser
from lumberjack.tokenizer import ApproxByteTokenizer
from lumberjack.transformer import PlainTextTransformer, TextTransformer


def test_tree_log_draft_chunk_pipeline_is_explicit() -> None:
    tree = Tree("# Guide\n\nBody", format="markdown")
    document = MarkdownParser().parse(tree)
    drafts = Lumberjack().splitter.split(document)
    chunks = ChunkFinalizer(ApproxByteTokenizer()).finalize(document, drafts)

    assert isinstance(document, DocTree)
    assert drafts and isinstance(drafts[0], ChunkDraft)
    assert chunks and chunks[0].body == "Body"


def test_normalizer_and_transformer_are_lossless_for_markup() -> None:
    text = "\ufeff# Title\r\n\r\n**bold**  \r\n\x00"
    seasoned = TextNormalizer().normalize(text)
    planed = TextTransformer().transform(seasoned)

    assert planed == "# Title\n\n**bold**  "


def test_transformer_preserves_markdown_hard_breaks_and_code_whitespace() -> None:
    text = "First line  \nSecond line\n\n```text\nvalue  \n```"

    assert TextTransformer().transform(text) == text


def test_plain_text_transformer_is_explicit_and_preserves_readable_content() -> None:
    text = (
        "# Title\n\nA **bold** and *soft* [link](https://example.com). "
        "Keep snake_case.\n\n```py\nprint('x')\n```"
    )

    assert TextTransformer().transform(text) == text
    assert PlainTextTransformer().transform(text) == (
        "Title\n\nA bold and soft link. Keep snake_case.\n\nprint('x')"
    )


def test_lumberjack_calls_custom_stages_in_order() -> None:
    calls: list[str] = []
    document = DocTree(title="T", source="", root=SectionNode(level=0, title="T"))
    draft = ChunkDraft(
        entries=[Entry(headings=(), body=" body ", start_line=1, end_line=1)],
        headings=(),
        own_heading=None,
        headings_token_count=0,
        body_token_count=2,
        token_count=2,
    )

    class Parser:
        block_kinds = frozenset({"paragraph"})

        def parse(self, tree: Tree) -> DocTree:
            del tree
            calls.append("parse")
            return document

    class Splitter:
        tokenizer = ApproxByteTokenizer()

        def split(self, document: DocTree) -> list[ChunkDraft]:
            assert document.title == "T"
            calls.append("split")
            return [draft]

    class TextNormalizer:
        def normalize(self, text: str) -> str:
            calls.append("normalize")
            return text.strip()

    class TextTransformer:
        def transform(self, text: str) -> str:
            calls.append("transform")
            return text.upper()

    jack = Lumberjack(
        parser=Parser(),
        splitter=Splitter(),
        normalizer=TextNormalizer(),
        transformer=TextTransformer(),
    )

    chunks = jack.saw(Tree("ignored"))

    assert calls == ["parse", "split", "normalize", "transform"]
    assert chunks[0].body == "BODY"


def test_lumberjack_rejects_a_splitter_using_a_different_tokenizer() -> None:
    splitter = Lumberjack().splitter

    with pytest.raises(ValueError, match="must share the same tokenizer"):
        Lumberjack(tokenizer=ApproxByteTokenizer(), splitter=splitter)
