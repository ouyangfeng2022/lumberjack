from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import lumberjack.scaler as tokenizers
from lumberjack.feller.markdown.feller import MarkdownItFeller
from lumberjack.models import Bundle, complete_heading_path, render_heading_path
from lumberjack.sawyer.context import SectionView
from lumberjack.scaler import (
    ApproxByteScaler,
    TiktokenScaler,
)
from tests.helpers import create_sawyer, create_scaler, saw, sawyer_options


@pytest.fixture(name="_local_tiktoken")
def local_tiktoken(monkeypatch: pytest.MonkeyPatch) -> None:
    class Encoding:
        def encode(self, text: str) -> list[int]:
            return list(text.encode("utf-8"))

    import tiktoken

    monkeypatch.setattr(tiktoken, "encoding_for_model", lambda _model: Encoding())


def test_split_entrypoints_pass_section_views_to_topology() -> None:
    """Both counting strategies must normalize sections before topology traversal."""
    from lumberjack.sawyer import ExactSectionSawyer, IncrementalSectionSawyer

    exact_seen: list[SectionView] = []
    incremental_seen: list[SectionView] = []

    class RecordingExactSectionSawyer(ExactSectionSawyer):
        def _split_section(self, section: SectionView) -> list[Bundle]:
            exact_seen.append(section)
            return super()._split_section(section)

    class RecordingIncrementalSectionSawyer(IncrementalSectionSawyer):
        def _split_section(self, section: SectionView) -> list[Bundle]:
            incremental_seen.append(section)
            return super()._split_section(section)

    document = MarkdownItFeller().fell("# A\n\nbody\n\n## B\n\nchild")
    scaler = ApproxByteScaler()

    RecordingExactSectionSawyer(scaler).saw(document)
    RecordingIncrementalSectionSawyer(scaler).saw(document)

    assert exact_seen
    assert incremental_seen
    assert all(section.body_tokens is None for section in exact_seen)
    assert all(section.body_tokens is not None for section in incremental_seen)
    assert all(section.title_tokens is not None for section in incremental_seen)
    assert all(section.subtree_tokens is not None for section in incremental_seen)
    assert all(section.tail_text is not None for section in incremental_seen)
    assert all(
        section.can_emit_as_single_chunk is not None for section in incremental_seen
    )


class TestApproxByteScaler:
    def test_count_is_bytes_div_3(self) -> None:
        tok = ApproxByteScaler()
        # "hello world" is 11 ASCII bytes -> 11 // 3 == 3
        assert tok.scale("hello world") == len(b"hello world") // 3

    def test_empty_string(self) -> None:
        assert ApproxByteScaler().scale("") == 0

    def test_unicode_counted_by_utf8_bytes(self) -> None:
        # Each CJK char is 3 UTF-8 bytes.
        assert ApproxByteScaler().scale("你好") == 6 // 3
        assert ApproxByteScaler().scale("你好世界你好世界") == 24 // 3

    def test_count_ignores_cache_kwarg(self) -> None:
        tok = ApproxByteScaler()
        assert tok.scale("hello world", cache=True) == len(b"hello world") // 3
        assert tok.scale("hello world", cache=False) == len(b"hello world") // 3

    def test_encode_returns_utf8_bytes(self) -> None:
        assert ApproxByteScaler().encode("anything") == tuple(b"anything")


class TestTiktokenDefaultCache:
    def test_default_cache_false_does_not_populate_cache(self, _local_tiktoken) -> None:
        tok = TiktokenScaler()
        assert tok.default_cache is False
        text = "hello world cache test"
        tok.scale(text)
        # cache not populated on a non-cache call
        assert text not in tok._cache

    def test_default_cache_true_populates_cache(self, _local_tiktoken) -> None:
        tok = TiktokenScaler(default_cache=True)
        text = "hello world cache test"
        tok.scale(text)
        assert text in tok._cache

    def test_explicit_cache_overrides_default(self, _local_tiktoken) -> None:
        tok = TiktokenScaler(default_cache=True)
        text = "explicit cache false"
        tok.scale(text, cache=False)
        assert text not in tok._cache


class TestTransformersScaler:
    def test_uses_fast_default_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, bool]] = []

        class FakeTokenizer:
            def encode(self, text: str) -> list[int]:
                return [ord(char) for char in text]

        fake_transformers = SimpleNamespace(
            AutoTokenizer=SimpleNamespace(
                from_pretrained=lambda model, use_fast=True: (
                    calls.append((model, use_fast)) or FakeTokenizer()
                )
            )
        )
        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

        tok = tokenizers.TransformersScaler()

        assert tok.encode("abc") == (97, 98, 99)
        assert tok.scale("abc") == 3
        assert calls == [("bert-base-uncased", True)]


class TestSeparatorDeltaAfter:
    """The sawyer's ``_separator_delta_after`` uses an 8-char tail window."""

    def _splitter(self):
        return create_sawyer(
            "incremental-sibling",
            ApproxByteScaler(),
            sawyer_options(max_tokens=1200),
        )

    def test_uses_8char_tail_window(self) -> None:
        sawyer = self._splitter()
        tok = sawyer.scaler
        text = "abcdefgh"
        assert sawyer._separator_delta_after(text) == (
            tok.scale("abcdefgh\n\n", cache=True) - tok.scale("abcdefgh", cache=True)
        )

    def test_window_truncates_long_tail(self) -> None:
        sawyer = self._splitter()
        tok = sawyer.scaler
        long_text = "x" * 80
        # _separator_delta_after only counts the last 8 chars of the tail.
        assert sawyer._separator_delta_after(long_text) == (
            tok.scale("xxxxxxxx\n\n", cache=True) - tok.scale("xxxxxxxx", cache=True)
        )

    def test_empty_text_returns_zero(self) -> None:
        assert self._splitter()._separator_delta_after("") == 0


class _RecordingCountTokenizer:
    """Tokenizer that records every ``count`` argument."""

    def __init__(self) -> None:
        self.counted: list[str] = []

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(ord(c) for c in text) if text else ()

    def scale(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        self.counted.append(text)
        return len(text)


class TestCreateTokenizer:
    def test_approx_is_supported(self) -> None:
        engine = create_scaler("approx")
        assert isinstance(engine, ApproxByteScaler)

    def test_tiktoken_is_supported(self, _local_tiktoken) -> None:
        engine = create_scaler("tiktoken")
        assert isinstance(engine, TiktokenScaler)

    def test_transformers_is_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def from_pretrained(model: str, use_fast: bool = True):
            assert model == "bert-base-uncased"
            assert use_fast is True
            return SimpleNamespace(encode=lambda text: [1] if text else [])

        fake_transformers = SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=from_pretrained)
        )
        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

        assert isinstance(create_scaler("transformers"), tokenizers.TransformersScaler)

    def test_unknown_tokenizer_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported scaler"):
            create_scaler("bogus")


class TestCreateSplitterTokenizerEngine:
    def test_default_tokenizer_is_approx_byte(self) -> None:
        sawyer = create_sawyer("sibling")
        assert isinstance(sawyer.scaler, ApproxByteScaler)

    def test_splitter_runs_with_custom_tokenizer(self) -> None:
        source = "# Root\n\n## Alpha\n\nAlpha body\n\n## Beta\n\nBeta body\n"
        document = MarkdownItFeller().fell(source)
        options = sawyer_options(max_tokens=20, merge_below_ratio=0.5)
        sawyer = create_sawyer(
            "sibling",
            _RecordingCountTokenizer(),
            options=options,
        )

        chunks = saw(sawyer, document)

        assert chunks


def _split_with(
    source: str,
    scaler: str,
    max_tokens: int = 1200,
):
    document = MarkdownItFeller().fell(source)
    engine = create_scaler(scaler)
    options = sawyer_options(max_tokens=max_tokens)
    sawyer = create_sawyer("sibling", engine, options=options)
    return saw(sawyer, document), engine


class TestChunkCounts:
    SOURCE = (
        "# Title\n\n"
        "First paragraph with some text.\n\n"
        "Second paragraph with more text.\n\n"
        "## Subsection\n\n"
        "Subsection body content here.\n"
    )

    def test_approx_token_count_is_bytes_div_3(self) -> None:
        chunks, _ = _split_with(self.SOURCE, "approx")
        engine = create_scaler("approx")
        for chunk in chunks:
            assert chunk.token_count == (
                chunk.headings_token_count
                + engine.scale("\n\n", cache=True)
                + chunk.body_token_count
            )

    def test_tiktoken_token_count_matches_full_recount(self, _local_tiktoken) -> None:
        chunks, _ = _split_with(self.SOURCE, "tiktoken")
        engine = create_scaler("tiktoken")
        for chunk in chunks:
            assert chunk.headings_token_count == engine.scale(
                render_heading_path(
                    complete_heading_path(
                        chunk.ancestor_headings,
                        chunk.own_heading,
                    )
                ),
                cache=True,
            )
            assert chunk.body_token_count == engine.scale(chunk.body, cache=True)
            assert chunk.token_count == (
                chunk.headings_token_count
                + engine.scale("\n\n", cache=True)
                + chunk.body_token_count
            )


class TestSplitterUsesTailWindow:
    """The sawyer joins entries via its 8-char tail window."""

    SOURCE = (
        "# Parent\n\n"
        "Parent body with enough text to matter here.\n\n"
        "## Child A\n\n"
        "Child A body content.\n\n"
        "## Child B\n\n"
        "Child B body content.\n"
    )

    def test_counts_8char_tail_window(self) -> None:
        document = MarkdownItFeller().fell(self.SOURCE)
        tok = _RecordingCountTokenizer()
        sawyer = create_sawyer(
            "incremental-sibling",
            tok,
            sawyer_options(max_tokens=40, merge_below_ratio=0.25),
        )
        saw(sawyer, document)
        # The sawyer estimates separators by counting the last 8 chars of a
        # tail plus the separator.  At least one such count must appear
        # (the 8-char tail + "\n\n").
        assert any(len(t) == 10 and t.endswith("\n\n") for t in tok.counted), (
            "sawyer should count an 8-char tail + separator"
        )


class TestComponentTokenizerSelection:
    def test_minimal_lumber_uses_approx(self) -> None:
        from lumberjack import Lumberjack

        chunks = Lumberjack().saw("# T\n\nbody\n")
        assert chunks
        assert chunks[0].token_count == (
            chunks[0].headings_token_count
            + create_scaler("approx").scale("\n\n", cache=True)
            + chunks[0].body_token_count
        )

    def test_manual_pipeline_accepts_tiktoken(self, _local_tiktoken) -> None:
        chunks, _ = _split_with("# T\n\nbody text here\n", "tiktoken")
        assert chunks

    def test_manual_pipeline_accepts_transformers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = SimpleNamespace(
            AutoTokenizer=SimpleNamespace(
                from_pretrained=lambda *_a, **_k: SimpleNamespace(
                    encode=lambda text: [1] * len(text) if text else []
                )
            )
        )
        monkeypatch.setitem(sys.modules, "transformers", fake)
        chunks, _ = _split_with("# T\n\nbody text here\n", "transformers")
        assert chunks

    def test_internal_boundary_rejects_unknown_tokenizer(self) -> None:
        with pytest.raises(ValueError, match="Unsupported scaler"):
            create_scaler("bogus")


class TestCliTokenizer:
    def test_default_tokenizer_is_approx(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["input.md"])
        assert args.tokenizer == "approx"

    def test_tokenizer_accepts_real_engines_only(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        for tokenizer in ("approx", "tiktoken", "transformers"):
            args = parser.parse_args(["input.md", "--tokenizer", tokenizer])
            assert args.tokenizer == tokenizer

        with pytest.raises(SystemExit):
            parser.parse_args(["input.md", "--tokenizer", "simple"])

    def test_no_token_counter_flag(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["input.md", "--token-counter", "accurate"])


class TestSplitterStrategyIsClassProperty:
    """Exact vs incremental is a property of the sawyer class, not the scaler."""

    def test_sibling_aliases_to_incremental(self) -> None:
        from lumberjack.sawyer import (
            ExactSiblingSawyer,
            IncrementalSiblingSawyer,
            SiblingSawyer,
        )

        assert SiblingSawyer is IncrementalSiblingSawyer
        assert isinstance(create_sawyer("sibling"), IncrementalSiblingSawyer)
        assert isinstance(create_sawyer("exact-sibling"), ExactSiblingSawyer)

    def test_subtree_aliases_to_incremental(self) -> None:
        from lumberjack.sawyer import (
            ExactSubtreeSawyer,
            IncrementalSubtreeSawyer,
            SubtreeSawyer,
        )

        assert SubtreeSawyer is IncrementalSubtreeSawyer
        assert isinstance(create_sawyer("subtree"), IncrementalSubtreeSawyer)
        assert isinstance(create_sawyer("exact-subtree"), ExactSubtreeSawyer)

    def test_incremental_variants_route_correctly(self) -> None:
        from lumberjack.sawyer import (
            IncrementalSiblingSawyer,
            IncrementalSubtreeSawyer,
        )

        assert isinstance(
            create_sawyer("incremental-sibling"), IncrementalSiblingSawyer
        )
        assert isinstance(
            create_sawyer("incremental-subtree"), IncrementalSubtreeSawyer
        )

    def test_exact_splitter_has_no_separator_delta(self) -> None:
        """Exact sawyer must not carry the incremental delta-window machinery."""
        sawyer = create_sawyer("exact-sibling", _RecordingCountTokenizer())
        assert not hasattr(sawyer, "_separator_delta_after")
        assert not hasattr(sawyer, "_measure_section")

    def test_tokenizer_does_not_drive_strategy(self) -> None:
        """The same scaler yields different strategies on different sawyer classes."""
        tok = _RecordingCountTokenizer()
        exact = create_sawyer("exact-sibling", tok)
        incr = create_sawyer("incremental-sibling", tok)
        # Same scaler instance, different counting machinery on the sawyer.
        assert hasattr(incr, "_separator_delta_after")
        assert not hasattr(exact, "_separator_delta_after")


class TestCliSplitterChoices:
    def test_default_splitter_is_sibling(self) -> None:
        from lumberjack.cli import build_parser

        args = build_parser().parse_args(["input.md"])
        assert args.splitter == "sibling"

    def test_accepts_all_strategy_names(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        for name in (
            "sibling",
            "subtree",
            "section",
            "exact-sibling",
            "incremental-sibling",
            "exact-subtree",
            "incremental-subtree",
            "exact-section",
            "incremental-section",
        ):
            assert parser.parse_args(["input.md", "--splitter", name]).splitter == name

    def test_rejects_unknown_splitter(self) -> None:
        from lumberjack.cli import build_parser

        with pytest.raises(SystemExit):
            build_parser().parse_args(["input.md", "--splitter", "bogus"])
