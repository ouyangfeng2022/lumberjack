from __future__ import annotations

from lumberjack.core.tokenizers import ApproxCharTokenizer


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
