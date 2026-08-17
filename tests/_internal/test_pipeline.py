from lumberjack._internal.block_splitter import BlockSplitter
from lumberjack._internal.pipeline import TokenizerRegistry, split_source
from lumberjack.tokenizer import TiktokenTokenizer
from tests.helpers import CharacterTokenizer


def test_pipeline_applies_merge_below_ratio_to_section_splitter() -> None:
    source = "# A\n\n" + "x " * 200
    unmerged = split_source(
        source,
        splitter="exact-section",
        tokenizer="approx",
        max_tokens=40,
        ideal_max_tokens_ratio=0.5,
        merge_below_ratio=0.0,
    )
    merged = split_source(
        source,
        splitter="exact-section",
        tokenizer="approx",
        max_tokens=40,
        ideal_max_tokens_ratio=0.5,
        merge_below_ratio=0.5,
    )

    assert len(unmerged.chunks) == 7
    assert len(merged.chunks) == 6
    assert merged.chunks[-1].body == (
        f"{unmerged.chunks[-2].body}\n\n{unmerged.chunks[-1].body}"
    )


def test_split_source_preserves_document_level_data() -> None:
    result = split_source(
        "---\nauthor: Ada\n---\n\n# Guide\n\nBody\n\n[ref]: /target",
        metadata_overrides={"team": "search"},
    )

    assert result.document.title == "Guide"
    assert result.document.metadata["author"] == "Ada"
    assert result.document.metadata["team"] == "search"
    assert result.document.reference_definitions == {
        "ref": {"destination": "/target", "title": ""}
    }
    assert result.chunks


def test_tokenizer_registry_reuses_backend_with_request_local_caches(
    monkeypatch,
) -> None:
    calls = 0

    class Encoding:
        def encode(self, text: str) -> list[int]:
            return list(text.encode("utf-8"))

    def encoding_for_model(_model: str) -> Encoding:
        nonlocal calls
        calls += 1
        return Encoding()

    import tiktoken

    monkeypatch.setattr(tiktoken, "encoding_for_model", encoding_for_model)
    registry = TokenizerRegistry()

    first = registry.create("tiktoken")
    second = registry.create("tiktoken")
    assert isinstance(first, TiktokenTokenizer)
    assert isinstance(second, TiktokenTokenizer)
    first.count("request one", cache=True)

    assert calls == 1
    assert first is not second
    assert first.encoding is second.encoding
    assert first._cache is not second._cache
    assert "request one" in first._cache
    assert "request one" not in second._cache


def test_hard_split_uses_sublinear_counts_per_piece() -> None:
    class CountingTokenizer(CharacterTokenizer):
        def __init__(self) -> None:
            self.calls = 0

        def count(self, text: str, *, cache: bool = False) -> int:
            self.calls += 1
            return super().count(text, cache=cache)

    tokenizer = CountingTokenizer()
    splitter = BlockSplitter(tokenizer, max_tokens=64, block_options={})

    pieces = splitter.hard_split("x" * 4096, 64)

    assert "".join(piece for piece, _ in pieces) == "x" * 4096
    assert all(tokens <= 64 for _, tokens in pieces)
    assert tokenizer.calls < 2000
