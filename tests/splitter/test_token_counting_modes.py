from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import lumberjack.tokenizer as tokenizers
from lumberjack.parser.markdown.parser import MarkdownItParser
from lumberjack.tokenizer import (
    ApproxCharTokenizer,
    TiktokenTokenizer,
)
from tests.helpers import create_splitter, create_tokenizer, splitter_options


def test_exact_and_incremental_splitters_expose_distinct_counting_contexts() -> None:
    """Topology code can depend on one normalized counting-context contract."""
    from lumberjack.splitter.context import (
        ExactCountingContext,
        IncrementalCountingContext,
        SectionView,
    )

    document = MarkdownItParser().parse("# A\n\nbody")
    from lumberjack.splitter import (
        ExactSectionSplitter,
        IncrementalSectionSplitter,
    )

    tokenizer = ApproxCharTokenizer()
    exact = ExactSectionSplitter(tokenizer)
    incremental = IncrementalSectionSplitter(tokenizer)

    exact_view = ExactCountingContext(exact).prepare(document.root)
    incremental_view = IncrementalCountingContext(incremental).prepare(document.root)

    assert isinstance(exact_view, SectionView)
    assert exact_view.body_tokens is None
    assert incremental_view.body_tokens is not None


class TestApproxCharTokenizer:
    def test_count_is_chars_div_4(self) -> None:
        tok = ApproxCharTokenizer()
        assert tok.count("hello world") == 11 // 4

    def test_empty_string(self) -> None:
        assert ApproxCharTokenizer().count("") == 0

    def test_unicode_counted_by_code_point(self) -> None:
        # "你好" is 2 code points; "//4" floors to 0
        assert ApproxCharTokenizer().count("你好") == 0
        assert ApproxCharTokenizer().count("你好世界你好世界") == 8 // 4

    def test_count_ignores_cache_kwarg(self) -> None:
        tok = ApproxCharTokenizer()
        assert tok.count("hello world", cache=True) == 11 // 4
        assert tok.count("hello world", cache=False) == 11 // 4

    def test_encode_is_placeholder(self) -> None:
        # encode is not used by the splitter; placeholder returns empty tuple
        assert ApproxCharTokenizer().encode("anything") == ()


class TestTiktokenDefaultCache:
    def test_default_cache_false_does_not_populate_cache(self) -> None:
        tok = TiktokenTokenizer()
        assert tok.default_cache is False
        text = "hello world cache test"
        tok.count(text)
        # cache not populated on a non-cache call
        assert text not in tok._cache

    def test_default_cache_true_populates_cache(self) -> None:
        tok = TiktokenTokenizer(default_cache=True)
        text = "hello world cache test"
        tok.count(text)
        assert text in tok._cache

    def test_explicit_cache_overrides_default(self) -> None:
        tok = TiktokenTokenizer(default_cache=True)
        text = "explicit cache false"
        tok.count(text, cache=False)
        assert text not in tok._cache


class TestTransformersTokenizer:
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

        tok = tokenizers.TransformersTokenizer()

        assert tok.encode("abc") == (97, 98, 99)
        assert tok.count("abc") == 3
        assert calls == [("bert-base-uncased", True)]


class TestSeparatorDeltaAfter:
    """The splitter's ``_separator_delta_after`` uses an 8-char tail window."""

    def _splitter(self):
        return create_splitter(
            "incremental-sibling",
            TiktokenTokenizer(),
            splitter_options(max_tokens=1200),
        )

    def test_uses_8char_tail_window(self) -> None:
        splitter = self._splitter()
        tok = splitter.tokenizer
        text = "abcdefgh"
        assert splitter._separator_delta_after(text) == (
            tok.count("abcdefgh\n\n", cache=True) - tok.count("abcdefgh", cache=True)
        )

    def test_window_truncates_long_tail(self) -> None:
        splitter = self._splitter()
        tok = splitter.tokenizer
        long_text = "x" * 80
        # _separator_delta_after only counts the last 8 chars of the tail.
        assert splitter._separator_delta_after(long_text) == (
            tok.count("xxxxxxxx\n\n", cache=True) - tok.count("xxxxxxxx", cache=True)
        )

    def test_empty_text_returns_zero(self) -> None:
        assert self._splitter()._separator_delta_after("") == 0


class _RecordingCountTokenizer:
    """Tokenizer that records every ``count`` argument."""

    def __init__(self) -> None:
        self.counted: list[str] = []

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(ord(c) for c in text) if text else ()

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        self.counted.append(text)
        return len(text)


class TestCreateTokenizer:
    def test_approx_is_supported(self) -> None:
        engine = create_tokenizer("approx")
        assert isinstance(engine, ApproxCharTokenizer)

    def test_tiktoken_is_supported(self) -> None:
        engine = create_tokenizer("tiktoken")
        assert isinstance(engine, TiktokenTokenizer)

    def test_transformers_is_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def from_pretrained(model: str, use_fast: bool = True):
            assert model == "bert-base-uncased"
            assert use_fast is True
            return SimpleNamespace(encode=lambda text: [1] if text else [])

        fake_transformers = SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=from_pretrained)
        )
        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

        assert isinstance(
            create_tokenizer("transformers"), tokenizers.TransformersTokenizer
        )

    def test_unknown_tokenizer_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported tokenizer"):
            create_tokenizer("bogus")


class TestCreateSplitterTokenizerEngine:
    def test_default_tokenizer_is_approx_char(self) -> None:
        splitter = create_splitter("sibling")
        assert isinstance(splitter.tokenizer, ApproxCharTokenizer)

    def test_splitter_runs_with_custom_tokenizer(self) -> None:
        source = "# Root\n\n## Alpha\n\nAlpha body\n\n## Beta\n\nBeta body\n"
        document = MarkdownItParser().parse(source)
        options = splitter_options(max_tokens=20, merge_below_ratio=0.5)
        splitter = create_splitter(
            "sibling",
            _RecordingCountTokenizer(),
            options=options,
        )

        chunks = splitter.split(document)

        assert chunks


def _split_with(
    source: str,
    tokenizer: str,
    max_tokens: int = 1200,
):
    document = MarkdownItParser().parse(source)
    engine = create_tokenizer(tokenizer)
    options = splitter_options(max_tokens=max_tokens)
    splitter = create_splitter("sibling", engine, options=options)
    return splitter.split(document), engine


class TestChunkCounts:
    SOURCE = (
        "# Title\n\n"
        "First paragraph with some text.\n\n"
        "Second paragraph with more text.\n\n"
        "## Subsection\n\n"
        "Subsection body content here.\n"
    )

    def test_approx_token_count_is_chars_div_4(self) -> None:
        chunks, _ = _split_with(self.SOURCE, "approx")
        for chunk in chunks:
            # token_count is always a full recount of the rendered body
            assert chunk.token_count == len(chunk.body) // 4

    def test_tiktoken_token_count_matches_full_recount(self) -> None:
        chunks, _ = _split_with(self.SOURCE, "tiktoken")
        engine = create_tokenizer("tiktoken")
        for chunk in chunks:
            # token_count is always a full cached recount of the rendered body
            assert chunk.token_count == engine.count(chunk.body, cache=True)


class TestSplitterUsesTailWindow:
    """The splitter joins entries via its 8-char tail window."""

    SOURCE = (
        "# Parent\n\n"
        "Parent body with enough text to matter here.\n\n"
        "## Child A\n\n"
        "Child A body content.\n\n"
        "## Child B\n\n"
        "Child B body content.\n"
    )

    def test_counts_8char_tail_window(self) -> None:
        document = MarkdownItParser().parse(self.SOURCE)
        tok = _RecordingCountTokenizer()
        splitter = create_splitter(
            "incremental-sibling",
            tok,
            splitter_options(max_tokens=40, merge_below_ratio=0.25),
        )
        splitter.split(document)
        # The splitter estimates separators by counting the last 8 chars of a
        # tail plus the separator.  At least one such count must appear
        # (the 8-char tail + "\n\n").
        assert any(len(t) == 10 and t.endswith("\n\n") for t in tok.counted), (
            "splitter should count an 8-char tail + separator"
        )


class TestComponentTokenizerSelection:
    def test_minimal_lumber_uses_approx(self) -> None:
        from lumberjack import lumber

        chunks = lumber("# T\n\nbody\n")
        assert chunks
        assert chunks[0].token_count == len(chunks[0].body) // 4

    def test_manual_pipeline_accepts_tiktoken(self) -> None:
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
        with pytest.raises(ValueError, match="Unsupported tokenizer"):
            create_tokenizer("bogus")


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
    """Exact vs incremental is a property of the splitter class, not the tokenizer."""

    def test_sibling_aliases_to_incremental(self) -> None:
        from lumberjack.splitter import (
            ExactSiblingSplitter,
            IncrementalSiblingSplitter,
            SiblingSplitter,
        )

        assert SiblingSplitter is IncrementalSiblingSplitter
        assert isinstance(create_splitter("sibling"), IncrementalSiblingSplitter)
        assert isinstance(create_splitter("exact-sibling"), ExactSiblingSplitter)

    def test_subtree_aliases_to_incremental(self) -> None:
        from lumberjack.splitter import (
            ExactSubtreeSplitter,
            IncrementalSubtreeSplitter,
            SubtreeSplitter,
        )

        assert SubtreeSplitter is IncrementalSubtreeSplitter
        assert isinstance(create_splitter("subtree"), IncrementalSubtreeSplitter)
        assert isinstance(create_splitter("exact-subtree"), ExactSubtreeSplitter)

    def test_incremental_variants_route_correctly(self) -> None:
        from lumberjack.splitter import (
            IncrementalSiblingSplitter,
            IncrementalSubtreeSplitter,
        )

        assert isinstance(
            create_splitter("incremental-sibling"), IncrementalSiblingSplitter
        )
        assert isinstance(
            create_splitter("incremental-subtree"), IncrementalSubtreeSplitter
        )

    def test_exact_splitter_has_no_separator_delta(self) -> None:
        """Exact splitter must not carry the incremental delta-window machinery."""
        splitter = create_splitter("exact-sibling", _RecordingCountTokenizer())
        assert not hasattr(splitter, "_separator_delta_after")
        assert not hasattr(splitter, "_measure_section")

    def test_tokenizer_does_not_drive_strategy(self) -> None:
        """The same tokenizer yields different strategies on different splitter classes."""
        tok = _RecordingCountTokenizer()
        exact = create_splitter("exact-sibling", tok)
        incr = create_splitter("incremental-sibling", tok)
        # Same tokenizer instance, different counting machinery on the splitter.
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
