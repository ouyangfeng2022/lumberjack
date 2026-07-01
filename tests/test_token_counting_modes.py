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


class TestStrategySeparatorDelta:
    def test_accurate_separator_delta_counts_full_text(self) -> None:
        tok = ApproxCharTokenizer()
        assert tok.separator_delta("abcdefgh", "\n\n") == 0

    def test_incremental_separator_delta_uses_8char_window(self) -> None:
        tok = TiktokenTokenizer(token_counter="incremental")
        assert tok.is_incremental is True
        assert tok.separator_delta("abcdefgh", "\n\n") == (
            tok.count("abcdefgh\n\n", cache=True) - tok.count("abcdefgh", cache=True)
        )

    def test_both_strategies_return_zero_for_empty_text(self) -> None:
        tok = ApproxCharTokenizer()
        assert tok.separator_delta("", "\n\n") == 0
        assert (
            TiktokenTokenizer(token_counter="incremental").separator_delta("", "\n\n")
            == 0
        )


class _BogusEngine:
    """Minimal stand-in engine that is not a real tokenizer."""

    def __init__(self, token_counter: str = "accurate") -> None:
        self.token_counter = token_counter

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return ()

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text)

    @property
    def is_incremental(self) -> bool:
        return self.token_counter == "incremental"

    def count_text(self, text: str) -> int:
        return self.count(text, cache=True)

    def count_budget_text(self, text: str, *, estimated_count: int) -> int:
        if self.token_counter == "incremental":
            return estimated_count
        return self.count_text(text)

    def count_estimated_text(self, text: str, *, estimated_count: int) -> int:
        if self.token_counter == "incremental":
            return estimated_count
        return self.count_text(text)

    def separator_delta(self, text: str, separator: str) -> int:
        if not text:
            return 0
        if self.is_incremental:
            text = text.rstrip("\n")[-8:]
        return self.count(f"{text}{separator}", cache=True) - self.count(
            text, cache=True
        )


class _NonAdditiveTokenizer:
    """Tokenizer that makes merged rendered content more expensive than parts."""

    token_counter = "accurate"

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return ()

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        if not text:
            return 0
        if "Alpha body" in text and "Beta body" in text:
            return 10
        return 1

    @property
    def is_incremental(self) -> bool:
        return False

    def count_text(self, text: str) -> int:
        return self.count(text, cache=True)

    def separator_delta(self, text: str, separator: str) -> int:
        if not text:
            return 0
        return self.count(f"{text}{separator}", cache=True) - self.count(
            text, cache=True
        )

    def count_budget_text(self, text: str, *, estimated_count: int) -> int:  # noqa: ARG002
        return self.count_text(text)

    def count_estimated_text(self, text: str, *, estimated_count: int) -> int:  # noqa: ARG002
        return self.count_text(text)


class _NoStrategyPeekTokenizer(_BogusEngine):
    @property
    def is_incremental(self) -> bool:
        raise AssertionError("splitter must not inspect tokenizer strategy")

    def separator_delta(self, text: str, separator: str) -> int:
        if not text:
            return 0
        return self.count(f"{text}{separator}", cache=True) - self.count(
            text, cache=True
        )

    def count_budget_text(self, text: str, *, estimated_count: int) -> int:  # noqa: ARG002
        return self.count_text(text)

    def count_estimated_text(self, text: str, *, estimated_count: int) -> int:  # noqa: ARG002
        return self.count_text(text)


class TestCreateTokenizerWithCounterMode:
    def test_approx_accurate_returns_approx_char(self) -> None:
        engine = create_tokenizer("approx", token_counter="accurate")
        assert isinstance(engine, ApproxCharTokenizer)
        assert engine.is_incremental is False

    def test_approx_incremental_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="does not support incremental"):
            create_tokenizer("approx", token_counter="incremental")

    def test_tiktoken_incremental_returns_incremental_tokenizer(self) -> None:
        engine = create_tokenizer("tiktoken", token_counter="incremental")
        assert isinstance(engine, TiktokenTokenizer)
        assert engine.is_incremental is True

    def test_tiktoken_accurate_forces_cache(self) -> None:
        engine = create_tokenizer("tiktoken", token_counter="accurate")
        assert isinstance(engine, TiktokenTokenizer)
        assert engine.default_cache is True
        assert engine.is_incremental is False

    def test_unknown_tokenizer_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported tokenizer"):
            create_tokenizer("bogus", token_counter="accurate")

    def test_unknown_token_counter_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported token_counter"):
            create_tokenizer("tiktoken", token_counter="bogus")


class TestCreateSplitterTokenizerCounter:
    def test_splitter_uses_tokenizer_counter_implementation(self) -> None:
        tokenizer = create_tokenizer("tiktoken", token_counter="incremental")
        splitter = create_splitter("recursive", tokenizer)
        assert splitter.token_counter is tokenizer  # ty: ignore[unresolved-attribute]

    def test_default_tokenizer_is_approx_char(self) -> None:
        splitter = create_splitter("recursive")
        assert isinstance(splitter.tokenizer, ApproxCharTokenizer)  # ty: ignore[unresolved-attribute]

    def test_splitter_does_not_inspect_tokenizer_strategy(self) -> None:
        source = "# Root\n\n## Alpha\n\nAlpha body\n\n## Beta\n\nBeta body\n"
        document = MarkdownItParser().parse(source)
        options = SplitOptions(max_tokens=20, merge_below_tokens=10)
        splitter = create_splitter(
            "recursive",
            _NoStrategyPeekTokenizer(),
            options=options,
        )

        chunks = splitter.split(document)

        assert chunks


class TestCreateTokenizer:
    def test_approx_is_supported(self) -> None:
        assert isinstance(create_tokenizer("approx"), ApproxCharTokenizer)

    def test_tiktoken_is_supported(self) -> None:
        assert isinstance(create_tokenizer("tiktoken"), TiktokenTokenizer)

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

    def test_simple_is_not_a_tokenizer_engine(self) -> None:
        with pytest.raises(ValueError, match="Unsupported tokenizer"):
            create_tokenizer("simple")


def _split_with_mode(
    source: str,
    tokenizer: str,
    token_counter: str,
    max_tokens: int = 1200,
):
    document = MarkdownItParser().parse(source)
    engine = create_tokenizer(tokenizer, token_counter=token_counter)
    options = SplitOptions(max_tokens=max_tokens)
    splitter = create_splitter("recursive", engine, options=options)
    return splitter.split(document), engine.token_counter


class TestThreeModeBoundaries:
    SOURCE = (
        "# Title\n\n"
        "First paragraph with some text.\n\n"
        "Second paragraph with more text.\n\n"
        "## Subsection\n\n"
        "Subsection body content here.\n"
    )

    def test_incremental_and_accurate_share_boundaries_on_tiktoken(self) -> None:
        incremental_chunks, _ = _split_with_mode(self.SOURCE, "tiktoken", "incremental")
        accurate_chunks, _ = _split_with_mode(self.SOURCE, "tiktoken", "accurate")
        # Same engine (tiktoken); boundaries match except where the incremental
        # approximation flips a borderline decision.  On this simple input the
        # document fits one chunk in both modes.
        assert len(incremental_chunks) == len(accurate_chunks)
        assert [c.start_line for c in incremental_chunks] == [
            c.start_line for c in accurate_chunks
        ]
        assert [c.end_line for c in incremental_chunks] == [
            c.end_line for c in accurate_chunks
        ]

    def test_approx_accurate_token_count_is_chars_div_4(self) -> None:
        chunks, _ = _split_with_mode(self.SOURCE, "approx", "accurate")
        for chunk in chunks:
            assert chunk.token_count == len(chunk.body) // 4
            # estimated_token_count equals token_count in accurate mode
            assert chunk.estimated_token_count == chunk.token_count

    def test_accurate_token_count_matches_full_recount(self) -> None:
        chunks, _ = _split_with_mode(self.SOURCE, "tiktoken", "accurate")
        engine = create_tokenizer("tiktoken", token_counter="accurate")
        for chunk in chunks:
            # accurate mode: token_count is the full cached recount
            assert chunk.token_count == engine.count(chunk.body, cache=True)


class TestSimpleTruncationGuard:
    def test_approx_truncates_per_chunk_not_per_block(self) -> None:
        # A document with several short blocks; the rendered body is the unit
        # of //4 truncation, not per-block.
        source = "# H\n\nab\n\ncd\n\nef\n\ng\n"
        chunks, _ = _split_with_mode(source, "approx", "accurate", max_tokens=100)
        assert chunks
        for chunk in chunks:
            assert chunk.token_count == len(chunk.body) // 4


class TestAccurateZeroEstimation:
    def test_accurate_uses_full_count_not_incremental_delta(self) -> None:
        # Construct a case where block-boundary token merging could make the
        # incremental delta differ from a full recount.  accurate mode must
        # report the full recount.
        source = "# Doc\n\nThe quick brown.\n\nfox jumps.\n\nover the lazy.\n\ndog.\n"
        chunks, _ = _split_with_mode(source, "tiktoken", "accurate", max_tokens=1200)
        engine = create_tokenizer("tiktoken", token_counter="accurate")
        for chunk in chunks:
            assert chunk.token_count == engine.count(chunk.body, cache=True)
            assert chunk.estimated_token_count == chunk.token_count

    def test_accurate_split_decisions_use_rendered_recount_not_merged_counts(
        self,
    ) -> None:
        source = "# Root\n\n## Alpha\n\nAlpha body\n\n## Beta\n\nBeta body\n"
        document = MarkdownItParser().parse(source)
        options = SplitOptions(
            max_tokens=5,
            ideal_max_tokens_ratio=1,
            merge_below_tokens=None,
        )
        splitter = create_splitter(
            "recursive",
            _NonAdditiveTokenizer(),
            options=options,
        )

        chunks = splitter.split(document)

        assert len(chunks) == 2
        assert [chunk.token_count for chunk in chunks] == [1, 1]
        assert all(
            "Alpha body" not in chunk.body or "Beta body" not in chunk.body
            for chunk in chunks
        )


class TestLumberTokenCounter:
    def test_lumber_accepts_approx_accurate(self) -> None:
        from lumberjack import lumber

        chunks = lumber("# T\n\nbody\n", tokenizer="approx", token_counter="accurate")
        assert chunks
        assert chunks[0].token_count == len(chunks[0].body) // 4

    def test_lumber_accepts_tiktoken_incremental(self) -> None:
        from lumberjack import lumber

        chunks = lumber(
            "# T\n\nbody text here\n",
            tokenizer="tiktoken",
            token_counter="incremental",
        )
        assert chunks

    def test_lumber_accepts_tiktoken_accurate(self) -> None:
        from lumberjack import lumber

        chunks = lumber(
            "# T\n\nbody text here\n",
            tokenizer="tiktoken",
            token_counter="accurate",
        )
        assert chunks

    def test_lumber_approx_accurate_uses_chars_div_4(self) -> None:
        from lumberjack import lumber

        chunks = lumber("# T\n\nbody text\n", tokenizer="approx")
        assert chunks[0].token_count == len(chunks[0].body) // 4

    def test_lumber_approx_incremental_is_rejected(self) -> None:
        from lumberjack import lumber

        with pytest.raises(ValueError, match="does not support incremental"):
            lumber(
                "# T\n\nbody text\n", tokenizer="approx", token_counter="incremental"
            )

    def test_lumber_unknown_token_counter_raises(self) -> None:
        from lumberjack import lumber

        with pytest.raises(ValueError, match="Unsupported token_counter"):
            lumber("# T\n\nbody\n", token_counter="bogus")

    def test_lumber_unknown_tokenizer_raises(self) -> None:
        from lumberjack import lumber

        with pytest.raises(ValueError, match="Unsupported tokenizer"):
            lumber("# T\n\nbody\n", token_counter="incremental", tokenizer="bogus")


class TestCliTokenCounter:
    def test_default_tokenizer_is_approx_accurate(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["input.md"])
        assert args.token_counter == "accurate"
        assert args.tokenizer == "approx"

    def test_token_counter_accepts_two_strategies(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        for mode in ("incremental", "accurate"):
            args = parser.parse_args(["input.md", "--token-counter", mode])
            assert args.token_counter == mode

    def test_token_counter_rejects_unknown(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["input.md", "--token-counter", "bogus"])

    def test_tokenizer_accepts_real_engines_only(self) -> None:
        from lumberjack.cli import build_parser

        parser = build_parser()
        for tokenizer in ("approx", "tiktoken", "transformers"):
            args = parser.parse_args(["input.md", "--tokenizer", tokenizer])
            assert args.tokenizer == tokenizer

        with pytest.raises(SystemExit):
            parser.parse_args(["input.md", "--tokenizer", "simple"])
