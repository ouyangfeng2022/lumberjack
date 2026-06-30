from __future__ import annotations

import pytest

from lumberjack.core.models import SplitOptions
from lumberjack.core.parsers.markdown.parser import MarkdownItParser
from lumberjack.core.splitters import create_splitter
from lumberjack.core.tokenizers import (
    ApproxCharTokenizer,
    ExactTokenCount,
    IncrementalTokenCount,
    SimpleCharTokenizer,
    TiktokenTokenizer,
    create_token_counter,
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
        tok = TiktokenTokenizer(default_cache=False)
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


class TestStrategyCountBody:
    def test_exact_count_body_is_non_additive(self) -> None:
        tok = SimpleCharTokenizer()
        strategy = ExactTokenCount(tok)
        # SimpleCharTokenizer counts chars, so "ab" + "\n\n" + "cd" = 6 chars
        assert strategy.count_body(["ab", "cd"], "\n\n") == 6

    def test_incremental_count_body_matches_exact_for_single_separator(self) -> None:
        tok = SimpleCharTokenizer()
        exact = ExactTokenCount(tok)
        incr = IncrementalTokenCount(tok)
        # With a char tokenizer the additive arithmetic equals the full count
        assert incr.count_body(["ab", "cd"], "\n\n") == exact.count_body(
            ["ab", "cd"], "\n\n"
        )

    def test_exact_count_body_single_part(self) -> None:
        tok = SimpleCharTokenizer()
        strategy = ExactTokenCount(tok)
        assert strategy.count_body(["abc"], "\n\n") == 3


class _BogusEngine:
    """Minimal stand-in engine that is not a real tokenizer."""

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return ()

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text)


class TestCreateTokenCounter:
    def test_simple_returns_approx_char_and_exact(self) -> None:
        engine, mode = create_token_counter("simple")
        assert isinstance(engine, ApproxCharTokenizer)
        assert mode == "exact"

    def test_simple_ignores_provided_tokenizer(self) -> None:
        provided = TiktokenTokenizer()
        engine, mode = create_token_counter("simple", provided)
        assert isinstance(engine, ApproxCharTokenizer)
        assert mode == "exact"

    def test_estimate_without_tokenizer_defaults_to_tiktoken_incremental(self) -> None:
        engine, mode = create_token_counter("estimate")
        assert isinstance(engine, TiktokenTokenizer)
        assert mode == "incremental"

    def test_estimate_with_simple_tokenizer_uses_provided_instance(self) -> None:
        # Per the spec, estimate/accurate use a provided engine instance
        # directly. Name-based "simple -> tiktoken" upgrade applies only when
        # a name is resolved (handled in lumber()), not to caller-supplied
        # instances.
        engine, mode = create_token_counter("estimate", SimpleCharTokenizer())
        assert isinstance(engine, SimpleCharTokenizer)
        assert mode == "incremental"

    def test_accurate_forces_cache_on_tiktoken_and_uses_exact(self) -> None:
        engine, mode = create_token_counter("accurate")
        assert isinstance(engine, TiktokenTokenizer)
        assert engine.default_cache is True
        assert mode == "exact"

    def test_accurate_with_existing_tiktoken_upgrades_cache(self) -> None:
        existing = TiktokenTokenizer()
        assert existing.default_cache is False
        engine, mode = create_token_counter("accurate", existing)
        assert isinstance(engine, TiktokenTokenizer)
        assert engine.default_cache is True
        assert mode == "exact"

    def test_unknown_token_counter_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported token_counter"):
            create_token_counter("bogus")

    def test_unknown_engine_name_is_not_validated_for_instances(self) -> None:
        # When the caller supplies an instance, no name validation runs.
        # Name validation happens inside create_tokenizer (called only when an
        # engine must be constructed), which is covered by its own tests.
        bogus = _BogusEngine()
        engine, mode = create_token_counter("estimate", bogus)
        assert engine is bogus
        assert mode == "incremental"


class TestCreateSplitterCountMode:
    def test_default_count_mode_is_exact(self) -> None:
        from lumberjack.core.tokenizers import ExactTokenCount

        splitter = create_splitter("recursive", SimpleCharTokenizer())
        assert isinstance(splitter.token_counter, ExactTokenCount)  # ty: ignore[unresolved-attribute]

    def test_explicit_incremental_mode(self) -> None:
        from lumberjack.core.tokenizers import IncrementalTokenCount

        splitter = create_splitter(
            "recursive", SimpleCharTokenizer(), count_mode="incremental"
        )
        assert isinstance(splitter.token_counter, IncrementalTokenCount)  # ty: ignore[unresolved-attribute]

    def test_explicit_exact_mode(self) -> None:
        from lumberjack.core.tokenizers import ExactTokenCount

        splitter = create_splitter(
            "recursive", SimpleCharTokenizer(), count_mode="exact"
        )
        assert isinstance(splitter.token_counter, ExactTokenCount)  # ty: ignore[unresolved-attribute]


def _split_with_mode(source: str, token_counter: str, max_tokens: int = 1200):
    document = MarkdownItParser().parse(source)
    engine, mode = create_token_counter(token_counter)
    options = SplitOptions(max_tokens=max_tokens)
    splitter = create_splitter("recursive", engine, options=options, count_mode=mode)
    return splitter.split(document), mode


class TestThreeModeBoundaries:
    SOURCE = (
        "# Title\n\n"
        "First paragraph with some text.\n\n"
        "Second paragraph with more text.\n\n"
        "## Subsection\n\n"
        "Subsection body content here.\n"
    )

    def test_estimate_and_accurate_share_boundaries_on_tiktoken(self) -> None:
        estimate_chunks, _ = _split_with_mode(self.SOURCE, "estimate")
        accurate_chunks, _ = _split_with_mode(self.SOURCE, "accurate")
        # Same engine (tiktoken); boundaries match except where the incremental
        # approximation flips a borderline decision.  On this simple input the
        # document fits one chunk in both modes.
        assert len(estimate_chunks) == len(accurate_chunks)
        assert [c.start_line for c in estimate_chunks] == [
            c.start_line for c in accurate_chunks
        ]
        assert [c.end_line for c in estimate_chunks] == [
            c.end_line for c in accurate_chunks
        ]

    def test_simple_token_count_is_chars_div_4(self) -> None:
        chunks, _ = _split_with_mode(self.SOURCE, "simple")
        for chunk in chunks:
            assert chunk.token_count == len(chunk.body) // 4
            # estimated_token_count equals token_count in simple mode
            assert chunk.estimated_token_count == chunk.token_count

    def test_accurate_token_count_matches_full_recount(self) -> None:
        chunks, _ = _split_with_mode(self.SOURCE, "accurate")
        engine, _ = create_token_counter("accurate")
        for chunk in chunks:
            # accurate mode: token_count is the full cached recount
            assert chunk.token_count == engine.count(chunk.body, cache=True)


class TestSimpleTruncationGuard:
    def test_simple_truncates_per_chunk_not_per_block(self) -> None:
        # A document with several short blocks; the rendered body is the unit
        # of //4 truncation, not per-block.
        source = "# H\n\nab\n\ncd\n\nef\n\ng\n"
        chunks, _ = _split_with_mode(source, "simple", max_tokens=100)
        assert chunks
        for chunk in chunks:
            assert chunk.token_count == len(chunk.body) // 4


class TestAccurateZeroEstimation:
    def test_accurate_uses_full_count_not_incremental_delta(self) -> None:
        # Construct a case where block-boundary token merging could make the
        # incremental delta differ from a full recount.  accurate mode must
        # report the full recount.
        source = "# Doc\n\nThe quick brown.\n\nfox jumps.\n\nover the lazy.\n\ndog.\n"
        chunks, _ = _split_with_mode(source, "accurate", max_tokens=1200)
        engine, _ = create_token_counter("accurate")
        for chunk in chunks:
            assert chunk.token_count == engine.count(chunk.body, cache=True)
            assert chunk.estimated_token_count == chunk.token_count


class TestLumberTokenCounter:
    def test_lumber_accepts_token_counter_simple(self) -> None:
        from lumberjack import lumber

        chunks = lumber("# T\n\nbody\n", token_counter="simple")
        assert chunks
        assert chunks[0].token_count == len(chunks[0].body) // 4

    def test_lumber_accepts_token_counter_estimate(self) -> None:
        from lumberjack import lumber

        chunks = lumber("# T\n\nbody text here\n", token_counter="estimate")
        assert chunks

    def test_lumber_accepts_token_counter_accurate(self) -> None:
        from lumberjack import lumber

        chunks = lumber("# T\n\nbody text here\n", token_counter="accurate")
        assert chunks

    def test_lumber_simple_ignores_tiktoken_engine(self) -> None:
        from lumberjack import lumber

        # token_counter=simple must ignore tokenizer=tiktoken and use chars//4
        chunks = lumber(
            "# T\n\nbody text\n", token_counter="simple", tokenizer="tiktoken"
        )
        assert chunks[0].token_count == len(chunks[0].body) // 4

    def test_lumber_estimate_uses_tiktoken_when_engine_is_simple(self) -> None:
        from lumberjack import lumber

        # The name->engine upgrade (simple -> tiktoken) happens in lumber()
        # for estimate/accurate, so this must not raise.
        chunks = lumber(
            "# T\n\nbody text\n",
            token_counter="estimate",
            tokenizer="simple",
        )
        assert chunks

    def test_lumber_unknown_token_counter_raises(self) -> None:
        from lumberjack import lumber

        with pytest.raises(ValueError, match="Unsupported token_counter"):
            lumber("# T\n\nbody\n", token_counter="bogus")

    def test_lumber_unknown_tokenizer_raises(self) -> None:
        from lumberjack import lumber

        with pytest.raises(ValueError, match="Unsupported tokenizer"):
            lumber("# T\n\nbody\n", token_counter="estimate", tokenizer="bogus")


class TestCliTokenCounter:
    def test_default_token_counter_is_simple(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["input.md"])
        assert args.token_counter == "simple"
        assert args.tokenizer == "simple"

    def test_token_counter_accepts_three_modes(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        for mode in ("simple", "estimate", "accurate"):
            args = parser.parse_args(["input.md", "--token-counter", mode])
            assert args.token_counter == mode

    def test_token_counter_rejects_unknown(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["input.md", "--token-counter", "bogus"])
