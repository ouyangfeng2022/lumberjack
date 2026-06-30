from __future__ import annotations

from lumberjack.core.tokenizers import (
    ApproxCharTokenizer,
    ExactTokenCount,
    IncrementalTokenCount,
    SimpleCharTokenizer,
    TiktokenTokenizer,
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
