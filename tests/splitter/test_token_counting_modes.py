from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import lumberjack.tokenizer as tokenizers
from lumberjack.finalizer import ChunkFinalizer
from lumberjack.models import (
    ChunkDraft,
    SourceLocation,
    complete_heading_path,
    render_draft_body,
    render_heading_path,
)
from lumberjack.parser import DocTreeBuilder
from lumberjack.parser.markdown.parser import MarkdownItParser
from lumberjack.splitter.context import SectionView
from lumberjack.splitter.record import RecordSplitter
from lumberjack.tokenizer import (
    ApproxByteTokenizer,
    TiktokenTokenizer,
)
from lumberjack.transformer import PlainTextTransformer
from tests.helpers import (
    CharacterTokenizer,
    create_splitter,
    create_tokenizer,
    saw,
    splitter_options,
)


@pytest.fixture(name="_local_tiktoken")
def local_tiktoken(monkeypatch: pytest.MonkeyPatch) -> None:
    class Encoding:
        def encode(self, text: str) -> list[int]:
            return list(text.encode("utf-8"))

    import tiktoken

    monkeypatch.setattr(tiktoken, "encoding_for_model", lambda _model: Encoding())


def test_split_entrypoints_pass_section_views_to_topology() -> None:
    """Both counting strategies must normalize sections before topology traversal."""
    from lumberjack.splitter import ExactSectionSplitter, IncrementalSectionSplitter

    exact_seen: list[SectionView] = []
    incremental_seen: list[SectionView] = []

    class RecordingExactSectionSplitter(ExactSectionSplitter):
        def _split_section(self, section: SectionView) -> list[ChunkDraft]:
            exact_seen.append(section)
            return super()._split_section(section)

    class RecordingIncrementalSectionSplitter(IncrementalSectionSplitter):
        def _split_section(self, section: SectionView) -> list[ChunkDraft]:
            incremental_seen.append(section)
            return super()._split_section(section)

    document = MarkdownItParser().parse("# A\n\nbody\n\n## B\n\nchild")
    tokenizer = ApproxByteTokenizer()

    RecordingExactSectionSplitter(tokenizer).split(document)
    RecordingIncrementalSectionSplitter(tokenizer).split(document)

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


class TestApproxByteTokenizer:
    def test_count_is_bytes_div_3(self) -> None:
        tok = ApproxByteTokenizer()
        # "hello world" is 11 ASCII bytes -> 11 // 3 == 3
        assert tok.count("hello world") == len(b"hello world") // 3

    def test_empty_string(self) -> None:
        assert ApproxByteTokenizer().count("") == 0

    def test_unicode_counted_by_utf8_bytes(self) -> None:
        # Each CJK char is 3 UTF-8 bytes.
        assert ApproxByteTokenizer().count("你好") == 6 // 3
        assert ApproxByteTokenizer().count("你好世界你好世界") == 24 // 3

    def test_count_ignores_cache_kwarg(self) -> None:
        tok = ApproxByteTokenizer()
        assert tok.count("hello world", cache=True) == len(b"hello world") // 3
        assert tok.count("hello world", cache=False) == len(b"hello world") // 3

    def test_encode_returns_utf8_bytes(self) -> None:
        assert ApproxByteTokenizer().encode("anything") == tuple(b"anything")


class TestTiktokenDefaultCache:
    def test_default_cache_false_does_not_populate_cache(self, _local_tiktoken) -> None:
        tok = TiktokenTokenizer()
        assert tok.default_cache is False
        text = "hello world cache test"
        tok.count(text)
        # cache not populated on a non-cache call
        assert text not in tok._cache

    def test_default_cache_true_populates_cache(self, _local_tiktoken) -> None:
        tok = TiktokenTokenizer(default_cache=True)
        text = "hello world cache test"
        tok.count(text)
        assert text in tok._cache

    def test_explicit_cache_overrides_default(self, _local_tiktoken) -> None:
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
            ApproxByteTokenizer(),
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


class _CacheFlagRecordingTokenizer:
    """Tokenizer that records the ``cache`` flag of every ``count`` call."""

    def __init__(self) -> None:
        self.cache_flags: list[bool] = []

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return tuple(ord(c) for c in text) if text else ()

    def count(self, text: str, *, cache: bool = False) -> int:
        self.cache_flags.append(cache)
        return len(text)


class TestSplitterCachePolicy:
    """Exact counting runs cache-free; incremental keeps cache-enabled counting.

    Every document's split starts from a zero tokenizer cache in production,
    and a single split offers essentially no cache reuse, so the exact
    recount must never enable the tokenizer text cache.
    """

    SOURCE = (
        "# Title\n\n"
        "First paragraph with some text to pack.\n\n"
        "## Subsection\n\n"
        "Subsection body content here.\n\n"
        "```python\n"
        "print('alpha')\nprint('beta')\nprint('gamma')\n"
        "print('delta')\nprint('epsilon')\n"
        "```\n"
    )

    def test_exact_split_never_requests_tokenizer_cache(self) -> None:
        tokenizer = _CacheFlagRecordingTokenizer()
        splitter = create_splitter(
            "exact-sibling", tokenizer, splitter_options(max_tokens=40)
        )

        assert splitter.use_tokenizer_cache is False
        splitter.split(MarkdownItParser().parse(self.SOURCE))

        # Construction (separator count) and every split-phase count —
        # including oversized-block pieces routed through BlockSplitter —
        # must run with the tokenizer cache disabled.
        assert tokenizer.cache_flags
        assert not any(tokenizer.cache_flags)

    def test_incremental_split_still_uses_cache(self) -> None:
        tokenizer = _CacheFlagRecordingTokenizer()
        splitter = create_splitter(
            "incremental-sibling", tokenizer, splitter_options(max_tokens=40)
        )

        assert splitter.use_tokenizer_cache is True
        splitter.split(MarkdownItParser().parse(self.SOURCE))

        assert tokenizer.cache_flags
        assert any(tokenizer.cache_flags)

    def test_exact_split_dedupes_identical_count_texts(self) -> None:
        """The per-split memo must encode every distinct text at most once.

        Repeated heading paths and bodies counted at both the call site and
        the draft builder must never reach the tokenizer twice within one
        split. Uses a budget large enough that no block is oversized, so the
        assertion covers only the mixin's own counting points.
        """
        tokenizer = _RecordingCountTokenizer()
        splitter = create_splitter(
            "exact-sibling", tokenizer, splitter_options(max_tokens=400)
        )

        splitter.split(MarkdownItParser().parse(self.SOURCE))

        assert len(tokenizer.counted) > 1
        assert len(tokenizer.counted) == len(set(tokenizer.counted))

    def test_exact_split_dedupes_block_splitter_piece_counts(self) -> None:
        """BlockSplitter counts share the exact memo across the boundary.

        With an oversized fenced block, BlockSplitter's wrapper, literal, and
        piece counts must land in the same per-split memo the mixin reads, so
        neither the full block text nor any piece is encoded twice.
        """
        tokenizer = _RecordingCountTokenizer()
        splitter = create_splitter(
            "exact-section", tokenizer, splitter_options(max_tokens=60)
        )

        splitter.split(MarkdownItParser().parse(self.SOURCE))

        assert len(tokenizer.counted) > 1
        assert len(tokenizer.counted) == len(set(tokenizer.counted))


class TestExactFinalizerReuse:
    """Exact split-time counts carry over to finalize when text is unchanged."""

    SOURCE = (
        "# Title\n\n"
        "First paragraph with some text to pack.\n\n"
        "## Subsection\n\n"
        "Subsection body content here.\n\n"
        "```python\n"
        "print('alpha')\nprint('beta')\nprint('gamma')\n"
        "print('delta')\nprint('epsilon')\n"
        "```\n"
    )

    def test_unchanged_body_skips_final_recount(self) -> None:
        tokenizer = _RecordingCountTokenizer()
        splitter = create_splitter(
            "exact-section", tokenizer, splitter_options(max_tokens=60)
        )
        document = MarkdownItParser().parse(self.SOURCE)
        drafts = splitter.split(document)
        counts_after_split = len(tokenizer.counted)

        chunks = ChunkFinalizer(tokenizer).finalize(document, drafts)

        assert chunks
        assert len(tokenizer.counted) == counts_after_split
        assert all(chunk.estimated_token_count == chunk.token_count for chunk in chunks)

    def test_changed_body_recounts(self) -> None:
        tokenizer = _RecordingCountTokenizer()
        splitter = create_splitter(
            "exact-section", tokenizer, splitter_options(max_tokens=60)
        )
        document = MarkdownItParser().parse(self.SOURCE)
        drafts = splitter.split(document)
        counts_after_split = len(tokenizer.counted)

        chunks = ChunkFinalizer(
            tokenizer,
            transformer=PlainTextTransformer(),
        ).finalize(document, drafts)

        assert chunks
        assert len(tokenizer.counted) > counts_after_split


class TestExactSubtreeFitChecks:
    """Subtree fit decisions prune with block counts before rendering."""

    SOURCE = (
        "# Root\n\n"
        + "alpha-body " * 40
        + "\n\n## Branch\n\n"
        + "beta-body " * 40
        + "\n"
    )

    def test_oversized_subtree_render_is_never_encoded(self) -> None:
        tokenizer = _RecordingCountTokenizer()
        splitter = create_splitter(
            "exact-subtree", tokenizer, splitter_options(max_tokens=50)
        )
        document = MarkdownItParser().parse(self.SOURCE)

        chunks = saw(splitter, document)

        assert chunks
        joined = "\n".join(chunk.body for chunk in chunks)
        assert "alpha-body" in joined
        assert "beta-body" in joined
        # The full subtree render starts with the root heading and contains
        # the deepest body; pruning must keep it out of the tokenizer.
        assert not any(
            text.startswith("# Root") and "beta-body" in text
            for text in tokenizer.counted
        )

    def test_collapsed_subtree_entries_skip_per_entry_counts(self) -> None:
        tokenizer = _RecordingCountTokenizer()
        splitter = create_splitter(
            "exact-subtree", tokenizer, splitter_options(max_tokens=10000)
        )
        document = MarkdownItParser().parse(self.SOURCE)

        drafts = splitter.split(document)

        assert len(drafts) == 1
        assert len(drafts[0].entries) == 2
        assert all(entry.body_token_count == 0 for entry in drafts[0].entries)
        assert drafts[0].body_token_count > 0


class TestRecordSplitterCountingPolicy:
    """The record splitter counts exactly, through the shared per-split memo."""

    def _document(self):
        builder = DocTreeBuilder(
            title="Rows", topology="records", block_kinds=["record"]
        )
        for index in range(4):
            builder.add_record(
                f"row-{index}-" + "x" * 90,
                locations=[SourceLocation(json_path=f"$.items[{index}]")],
            )
        return builder.build()

    def test_runs_cache_free_with_per_split_memo(self) -> None:
        tokenizer = _RecordingCountTokenizer()
        splitter = RecordSplitter(tokenizer, max_tokens=100)

        assert splitter.use_tokenizer_cache is False

        drafts = splitter.split(self._document())

        assert drafts
        assert len(tokenizer.counted) == len(set(tokenizer.counted))


class TestCreateTokenizer:
    def test_approx_is_supported(self) -> None:
        engine = create_tokenizer("approx")
        assert isinstance(engine, ApproxByteTokenizer)

    def test_tiktoken_is_supported(self, _local_tiktoken) -> None:
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
    def test_default_tokenizer_is_approx_byte(self) -> None:
        splitter = create_splitter("sibling")
        assert isinstance(splitter.tokenizer, ApproxByteTokenizer)

    def test_splitter_runs_with_custom_tokenizer(self) -> None:
        source = "# Root\n\n## Alpha\n\nAlpha body\n\n## Beta\n\nBeta body\n"
        document = MarkdownItParser().parse(source)
        options = splitter_options(max_tokens=20, merge_below_ratio=0.5)
        splitter = create_splitter(
            "sibling",
            _RecordingCountTokenizer(),
            options=options,
        )

        chunks = saw(splitter, document)

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
    return saw(splitter, document), engine


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
        engine = create_tokenizer("approx")
        for chunk in chunks:
            assert chunk.token_count == (
                chunk.headings_token_count
                + engine.count("\n\n", cache=True)
                + chunk.body_token_count
            )

    def test_tiktoken_token_count_matches_full_recount(self, _local_tiktoken) -> None:
        chunks, _ = _split_with(self.SOURCE, "tiktoken")
        engine = create_tokenizer("tiktoken")
        for chunk in chunks:
            assert chunk.headings_token_count == engine.count(
                render_heading_path(
                    complete_heading_path(
                        chunk.ancestor_headings,
                        chunk.own_heading,
                    )
                ),
                cache=True,
            )
            assert chunk.body_token_count == engine.count(chunk.body, cache=True)
            assert chunk.token_count == (
                chunk.headings_token_count
                + engine.count("\n\n", cache=True)
                + chunk.body_token_count
            )


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
        saw(splitter, document)
        # The splitter estimates separators by counting the last 8 chars of a
        # tail plus the separator.  At least one such count must appear
        # (the 8-char tail + "\n\n").
        assert any(len(t) == 10 and t.endswith("\n\n") for t in tok.counted), (
            "splitter should count an 8-char tail + separator"
        )


class TestComponentTokenizerSelection:
    def test_minimal_lumber_uses_approx(self) -> None:
        from lumberjack import Lumberjack

        result = Lumberjack().saw("# T\n\nbody\n")
        assert result.chunks
        assert result.chunks[0].token_count == (
            result.chunks[0].headings_token_count
            + create_tokenizer("approx").count("\n\n", cache=True)
            + result.chunks[0].body_token_count
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

    def test_no_tokenizer_flag(self) -> None:
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
    def test_default_splitter_is_section(self) -> None:
        from lumberjack.cli import build_parser

        args = build_parser().parse_args(["input.md"])
        assert args.splitter == "section"

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


class TestLowerBoundRejections:
    """Sound part-sum bounds skip provably doomed encodes without flips."""

    def test_approx_count_skips_tuple_materialization(self) -> None:
        """count() must not route through encode()'s per-byte int tuple."""

        class EncodeSpyTokenizer(ApproxByteTokenizer):
            def __init__(self) -> None:
                super().__init__()
                self.encode_calls = 0

            def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:
                self.encode_calls += 1
                return super().encode(text, cache=cache)

        tokenizer = EncodeSpyTokenizer()

        for text in ("", "hello", "héllo wörld", "x" * 10_000):
            assert tokenizer.count(text) == len(text.encode("utf-8")) // 3

        assert tokenizer.encode_calls == 0
        assert tokenizer.encode("hi") == (104, 105)

    def test_exact_sibling_merge_bound_matches_full_recount(self) -> None:
        """Pre-rejecting provably overflowing merges never changes the drafts."""
        source = (
            "# Root\n\n"
            + "intro body\n\n"
            + "## A\n\n"
            + "alpha " * 60
            + "\n\n"
            + "## B\n\n"
            + "beta " * 60
            + "\n\n"
            + "## C\n\n"
            + "gamma " * 60
            + "\n"
        )
        document = MarkdownItParser().parse(source)
        tokenizer = _RecordingCountTokenizer()
        splitter = create_splitter(
            "exact-sibling", tokenizer, splitter_options(max_tokens=60)
        )
        bounded = splitter.split(document)

        splitter._merge_bound_exceeds = lambda *_: False  # type: ignore[method-assign]
        unbounded = splitter.split(document)

        assert [(d.headings, d.body_token_count, d.token_count) for d in bounded] == [
            (d.headings, d.body_token_count, d.token_count) for d in unbounded
        ]
        assert bounded

    def test_pack_parts_rejects_provably_overflowing_join(self) -> None:
        from lumberjack._internal.block_splitter import BlockSplitter

        tokenizer = _RecordingCountTokenizer()
        splitter = BlockSplitter(
            tokenizer,
            max_tokens=15,
            block_options={},
            use_cache=False,
            count_fn=None,
        )
        left = "a" * 30
        right = "b" * 30

        packed = splitter.pack_parts(
            [left, right], 15, separator="\n", part_token_counts=[10, 10]
        )

        # The recording tokenizer counts characters, so the first piece
        # carries its encoded count (30) and the second its part count (10);
        # the grouping is what matters — the join cannot fit 15.
        assert packed == [(left, 30), (right, 10)]
        # The doomed join (>= 10 + 10 - 2 > 15) was never encoded.
        assert f"{left}\n{right}" not in tokenizer.counted

    def test_pack_parts_exact_check_decides_within_bound_slack(self) -> None:
        from lumberjack._internal.block_splitter import BlockSplitter

        tokenizer = _RecordingCountTokenizer()
        splitter = BlockSplitter(
            tokenizer,
            max_tokens=2,
            block_options={},
            use_cache=False,
            count_fn=None,
        )

        # Single-character parts: 1 + 1 - 2 = 0 <= 2, so the bound must not
        # reject and the exact join check decides ("a\nb" counts 3 > 2).
        packed = splitter.pack_parts(
            ["a", "b"], 2, separator="\n", part_token_counts=[1, 1]
        )

        assert packed == [("a", 1), ("b", 1)]
        assert "a\nb" in tokenizer.counted


class _JoinCollapsingTokenizer:
    """Tokenizer violating TokenizerProtocol's join-counting property.

    Any text containing a blank line collapses to one token, so joining two
    parts can save far more than the two tokens of slack the pruning bounds
    allow.
    """

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return (1,) if "\n\n" in text else tuple(ord(char) for char in text)

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return 1 if "\n\n" in text else len(text)


class TestBoundContract:
    """The pruning bounds assume TokenizerProtocol's join-counting property.

    With a contract-violating tokenizer the bound is no longer sound: it
    rejects joins a full recount would accept.  This test pins that
    documented limitation instead of pretending it cannot happen — grouping
    changes, but no content is ever lost.
    """

    def test_join_collapsing_tokenizer_changes_grouping_not_content(self) -> None:
        source = (
            "# Root\n\n## Alpha\n\n" + "a" * 40 + "\n\n## Beta\n\n" + "b" * 40 + "\n"
        )
        document = MarkdownItParser().parse(source)
        splitter = create_splitter(
            "exact-sibling",
            _JoinCollapsingTokenizer(),
            splitter_options(max_tokens=60),
        )

        bounded = splitter.split(document)
        splitter._merge_bound_exceeds = lambda *_args, **_kwargs: False  # type: ignore[method-assign]
        unbounded = splitter.split(document)

        assert len(bounded) > len(unbounded)
        assert len(unbounded) == 1
        # Either way every record survives exactly once.
        for drafts in (bounded, unbounded):
            joined = "\n\n".join(
                render_draft_body(draft.entries, draft.headings) for draft in drafts
            )
            assert joined.count("a" * 40) == 1
            assert joined.count("b" * 40) == 1
        unbounded_body = render_draft_body(unbounded[0].entries, unbounded[0].headings)
        assert "a" * 40 in unbounded_body
        assert "b" * 40 in unbounded_body


EQUIVALENCE_SOURCES = {
    "merge-heavy": (
        "# Root\n\n"
        "Intro paragraph with ordinary body text.\n\n"
        "## Alpha\n\n" + "alpha body " * 25 + "\n\n"
        "## Beta\n\n" + "beta body " * 25 + "\n\n"
        "### Beta Child\n\n" + "child body text " * 8 + "\n\n"
        "## Gamma\n\n" + "gamma body " * 25 + "\n"
    ),
    "oversized-blocks": (
        "# Root\n\n"
        + "overflow paragraph " * 30
        + "\n\n```python\n"
        + "\n".join(f"print('statement number {i}')" for i in range(24))
        + "\n```\n\n"
        + "".join(f"- {'list item with words ' * 5}\n" for _ in range(4))
        + "\n| head one | head two |\n"
        "| --- | --- |\n"
        + "\n".join(f"| row {i} alpha | row {i} beta |" for i in range(12))
        + "\n"
    ),
}


def _disable_bounds(splitter) -> None:
    """Turn off every pre-rejection bound, keeping counting identical."""
    from lumberjack._internal.block_splitter import BlockSplitter

    splitter._merge_bound_exceeds = lambda *_args, **_kwargs: False
    splitter._subtree_body_token_bound = lambda _section: -(2**62)  # type: ignore[assignment]
    block_splitter = splitter._block_splitter
    unbounded_pack = BlockSplitter.pack_parts

    def pack_parts_unbounded(
        parts,
        max_tokens,
        *,
        separator,
        part_token_counts=None,  # noqa: ARG001
    ):
        """Drop the caller's part counts so every join is decided by recount."""
        return unbounded_pack(
            block_splitter,
            parts,
            max_tokens,
            separator=separator,
            part_token_counts=None,
        )

    block_splitter.pack_parts = pack_parts_unbounded


class TestBoundEquivalence:
    """Bounded pruning never changes split output for contract-abiding tokenizers.

    Every exact topology runs each source at several budgets under three
    tokenizers (real approx, character counting, offline tiktoken), with all
    pre-rejection bounds disabled for the second run; the bounded drafts
    must equal the unbounded ones draft for draft.
    """

    @pytest.mark.parametrize("source_name", sorted(EQUIVALENCE_SOURCES))
    @pytest.mark.parametrize("tokenizer_name", ["approx", "chars", "tiktoken"])
    @pytest.mark.parametrize("max_tokens", [40, 120, 400])
    @pytest.mark.parametrize(
        "splitter_name", ["exact-section", "exact-subtree", "exact-sibling"]
    )
    def test_bounded_split_matches_unbounded(
        self,
        splitter_name: str,
        max_tokens: int,
        tokenizer_name: str,
        source_name: str,
        _local_tiktoken,
    ) -> None:
        document = MarkdownItParser().parse(EQUIVALENCE_SOURCES[source_name])
        if tokenizer_name == "approx":
            tokenizer = ApproxByteTokenizer()
        elif tokenizer_name == "tiktoken":
            tokenizer = create_tokenizer("tiktoken")
        else:
            tokenizer = CharacterTokenizer()
        splitter = create_splitter(
            splitter_name, tokenizer, splitter_options(max_tokens=max_tokens)
        )

        bounded = splitter.split(document)

        _disable_bounds(splitter)
        unbounded = splitter.split(document)

        assert bounded
        assert bounded == unbounded

    def test_record_packing_matches_unbounded_reference(self) -> None:
        """The record join bound must not change greedy packing decisions."""
        texts = [f"row-{index} " + "x" * (30 + (index % 5) * 17) for index in range(24)]
        texts.append("huge " + "y" * 300)
        tokenizer = _RecordingCountTokenizer()
        splitter = RecordSplitter(tokenizer, max_tokens=120)
        builder = DocTreeBuilder(
            title="Rows", topology="records", block_kinds=["record"]
        )
        for index, text in enumerate(texts):
            builder.add_record(
                text, locations=[SourceLocation(json_path=f"$.items[{index}]")]
            )

        drafts = splitter.split(builder.build())

        # Reference packer with the bound removed: greedy accumulate,
        # full recount each step, protected emit for lone overflows.
        separator_tokens = splitter.separator_token_count
        expected: list[tuple[str, bool]] = []
        current: list[str] = []

        def rendered(group: list[str]) -> str:
            return "\n\n".join(text for text in group if text)

        for text in texts:
            candidate = [*current, text]
            candidate_tokens = separator_tokens + len(rendered(candidate))
            if current and candidate_tokens > splitter.ideal_max_tokens:
                expected.append((rendered(current), False))
                current = [text]
            else:
                current = candidate
            if len(current) == 1 and separator_tokens + len(text) > splitter.max_tokens:
                expected.append((text, True))
                current = []
        if current:
            expected.append((rendered(current), False))

        assert [
            (render_draft_body(draft.entries, ()), draft.protected) for draft in drafts
        ] == expected
        assert any(protected for _, protected in expected)
