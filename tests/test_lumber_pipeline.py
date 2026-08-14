from __future__ import annotations

import pytest

from lumberjack import Lumberjack, Tree
from lumberjack.feller import MarkdownFeller
from lumberjack.mill import Mill
from lumberjack.models import Bundle, Entry, Log, SectionNode
from lumberjack.planer import PlainTextPlaner, Planer
from lumberjack.scaler import ApproxByteScaler
from lumberjack.seasoner import Seasoner


def test_tree_log_bundle_chunk_pipeline_is_explicit() -> None:
    tree = Tree("# Guide\n\nBody", format="markdown")
    log = MarkdownFeller().fell(tree)
    bundles = Lumberjack().sawyer.saw(log)
    chunks = Mill(ApproxByteScaler()).mill(log, bundles)

    assert isinstance(log, Log)
    assert bundles and isinstance(bundles[0], Bundle)
    assert chunks and chunks[0].body == "Body"


def test_seasoner_and_planer_are_lossless_for_markup() -> None:
    text = "\ufeff# Title\r\n\r\n**bold**  \r\n\x00"
    seasoned = Seasoner().season(text)
    planed = Planer().plane(seasoned)

    assert planed == "# Title\n\n**bold**  "


def test_planer_preserves_markdown_hard_breaks_and_code_whitespace() -> None:
    text = "First line  \nSecond line\n\n```text\nvalue  \n```"

    assert Planer().plane(text) == text


def test_plain_text_planer_is_explicit_and_preserves_readable_content() -> None:
    text = (
        "# Title\n\nA **bold** and *soft* [link](https://example.com). "
        "Keep snake_case.\n\n```py\nprint('x')\n```"
    )

    assert Planer().plane(text) == text
    assert PlainTextPlaner().plane(text) == (
        "Title\n\nA bold and soft link. Keep snake_case.\n\nprint('x')"
    )


def test_lumberjack_calls_custom_stages_in_order() -> None:
    calls: list[str] = []
    log = Log(title="T", source="", root=SectionNode(level=0, title="T"))
    bundle = Bundle(
        entries=[Entry(headings=(), body=" body ", start_line=1, end_line=1)],
        headings=(),
        own_heading=None,
        headings_token_count=0,
        body_token_count=2,
        token_count=2,
    )

    class Feller:
        block_kinds = frozenset({"paragraph"})

        def fell(self, tree: Tree) -> Log:
            del tree
            calls.append("fell")
            return log

    class Sawyer:
        scaler = ApproxByteScaler()

        def saw(self, log: Log) -> list[Bundle]:
            assert log.title == "T"
            calls.append("saw")
            return [bundle]

    class Seasoner:
        def season(self, text: str) -> str:
            calls.append("season")
            return text.strip()

    class Planer:
        def plane(self, text: str) -> str:
            calls.append("plane")
            return text.upper()

    jack = Lumberjack(
        feller=Feller(),
        sawyer=Sawyer(),
        seasoner=Seasoner(),
        planer=Planer(),
    )

    chunks = jack.saw(Tree("ignored"))

    assert calls == ["fell", "saw", "season", "plane"]
    assert chunks[0].body == "BODY"


def test_lumberjack_rejects_a_sawyer_using_a_different_scaler() -> None:
    sawyer = Lumberjack().sawyer

    with pytest.raises(ValueError, match="must share the same scaler"):
        Lumberjack(scaler=ApproxByteScaler(), sawyer=sawyer)
