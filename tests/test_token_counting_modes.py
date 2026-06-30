from __future__ import annotations

import pytest

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
        assert isinstance(splitter.token_counter, ExactTokenCount)

    def test_explicit_incremental_mode(self) -> None:
        from lumberjack.core.tokenizers import IncrementalTokenCount

        splitter = create_splitter(
            "recursive", SimpleCharTokenizer(), count_mode="incremental"
        )
        assert isinstance(splitter.token_counter, IncrementalTokenCount)

    def test_explicit_exact_mode(self) -> None:
        from lumberjack.core.tokenizers import ExactTokenCount

        splitter = create_splitter(
            "recursive", SimpleCharTokenizer(), count_mode="exact"
        )
        assert isinstance(splitter.token_counter, ExactTokenCount)
