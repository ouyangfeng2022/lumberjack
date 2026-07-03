from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import lumberjack.core.tokenizers as tokenizers
from lumberjack.core.models import SplitOptions
from lumberjack.core.parsers.markdown.parser import MarkdownItParser
from lumberjack.core.splitters import create_splitter
from lumberjack.core.tokenizers import (
    ApproxCharTokenizer,
    TiktokenTokenizer,
    create_tokenizer,
)


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
            "incremental-recursive",
            TiktokenTokenizer(),
            SplitOptions(max_tokens=1200),
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
        splitter = create_splitter("recursive")
        assert isinstance(splitter.tokenizer, ApproxCharTokenizer)  # ty: ignore[unresolved-attribute]

    def test_splitter_runs_with_custom_tokenizer(self) -> None:
        source = "# Root\n\n## Alpha\n\nAlpha body\n\n## Beta\n\nBeta body\n"
        document = MarkdownItParser().parse(source)
        options = SplitOptions(max_tokens=20, merge_below_ratio=0.5)
        splitter = create_splitter(
            "recursive",
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
    options = SplitOptions(max_tokens=max_tokens)
    splitter = create_splitter("recursive", engine, options=options)
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
            "incremental-recursive",
            tok,
            SplitOptions(max_tokens=40, merge_below_ratio=0.25),
        )
        splitter.split(document)
        # The splitter estimates separators by counting the last 8 chars of a
        # tail plus the separator.  At least one such count must appear
        # (the 8-char tail + "\n\n").
        assert any(len(t) == 10 and t.endswith("\n\n") for t in tok.counted), (
            "splitter should count an 8-char tail + separator"
        )


class TestLumberTokenizer:
    def test_lumber_accepts_approx(self) -> None:
        from lumberjack import lumber

        chunks = lumber("# T\n\nbody\n", tokenizer="approx")
        assert chunks
        assert chunks[0].token_count == len(chunks[0].body) // 4

    def test_lumber_accepts_tiktoken(self) -> None:
        from lumberjack import lumber

        chunks = lumber("# T\n\nbody text here\n", tokenizer="tiktoken")
        assert chunks

    def test_lumber_accepts_transformers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lumberjack import lumber

        fake = SimpleNamespace(
            AutoTokenizer=SimpleNamespace(
                from_pretrained=lambda *_a, **_k: SimpleNamespace(
                    encode=lambda text: [1] * len(text) if text else []
                )
            )
        )
        monkeypatch.setitem(sys.modules, "transformers", fake)
        chunks = lumber("# T\n\nbody text here\n", tokenizer="transformers")
        assert chunks

    def test_lumber_unknown_tokenizer_raises(self) -> None:
        from lumberjack import lumber

        with pytest.raises(ValueError, match="Unsupported tokenizer"):
            lumber("# T\n\nbody\n", tokenizer="bogus")


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

    def test_recursive_aliases_to_exact(self) -> None:
        from lumberjack.core.splitters import (
            ExactRecursiveSplitter,
            RecursiveSplitter,
        )

        assert RecursiveSplitter is ExactRecursiveSplitter
        assert isinstance(create_splitter("recursive"), ExactRecursiveSplitter)
        assert isinstance(create_splitter("exact-recursive"), ExactRecursiveSplitter)

    def test_section_aliases_to_exact(self) -> None:
        from lumberjack.core.splitters import (
            ExactSectionSplitter,
            SectionSplitter,
        )

        assert SectionSplitter is ExactSectionSplitter
        assert isinstance(create_splitter("section"), ExactSectionSplitter)
        assert isinstance(create_splitter("exact-section"), ExactSectionSplitter)

    def test_incremental_variants_route_correctly(self) -> None:
        from lumberjack.core.splitters import (
            IncrementalRecursiveSplitter,
            IncrementalSectionSplitter,
        )

        assert isinstance(
            create_splitter("incremental-recursive"), IncrementalRecursiveSplitter
        )
        assert isinstance(
            create_splitter("incremental-section"), IncrementalSectionSplitter
        )

    def test_exact_splitter_has_no_separator_delta(self) -> None:
        """Exact splitter must not carry the incremental delta-window machinery."""
        splitter = create_splitter("exact-recursive", _RecordingCountTokenizer())
        assert not hasattr(splitter, "_separator_delta_after")
        assert not hasattr(splitter, "_measure_section")

    def test_tokenizer_does_not_drive_strategy(self) -> None:
        """The same tokenizer yields different strategies on different splitter classes."""
        tok = _RecordingCountTokenizer()
        exact = create_splitter("exact-recursive", tok)
        incr = create_splitter("incremental-recursive", tok)
        # Same tokenizer instance, different counting machinery on the splitter.
        assert hasattr(incr, "_separator_delta_after")
        assert not hasattr(exact, "_separator_delta_after")


class TestCliSplitterChoices:
    def test_default_splitter_is_recursive(self) -> None:
        from lumberjack.cli import build_parser

        args = build_parser().parse_args(["input.md"])
        assert args.splitter == "recursive"

    def test_accepts_all_strategy_names(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        for name in (
            "recursive",
            "section",
            "exact-recursive",
            "incremental-recursive",
            "exact-section",
            "incremental-section",
        ):
            assert parser.parse_args(["input.md", "--splitter", name]).splitter == name

    def test_rejects_unknown_splitter(self) -> None:
        from lumberjack.cli import build_parser

        with pytest.raises(SystemExit):
            build_parser().parse_args(["input.md", "--splitter", "bogus"])
