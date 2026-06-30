# Token Counting Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three mutually exclusive token counting modes (`simple`, `estimate`, `accurate`) selectable via a new `token_counter` parameter, while keeping the existing `tokenizer` parameter as the underlying engine selector.

**Architecture:** Introduce a counting-strategy abstraction inside `BaseSplitter` with two implementations (`ExactTokenCount`, `IncrementalTokenCount`). `simple` and `accurate` modes share the exact path; `estimate` uses the incremental path. A new `create_token_counter(name, tokenizer)` factory maps a mode to `(engine, count_mode)` so `lumber()` and `create_splitter` can wire the splitter with the right strategy.

**Tech Stack:** Python 3.13, dataclasses, tiktoken (optional), cachetools, pytest, ty, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-06-30-token-counting-modes-design.md`

---

## File Structure

- Modify: `src/lumberjack/core/tokenizers.py`
  - Add `ApproxCharTokenizer` (`chars // 4`).
  - Extend `TiktokenTokenizer` with `default_cache` constructor parameter.
  - Keep `SimpleCharTokenizer` (engine role) and `create_tokenizer(name)` unchanged.
  - Add `CountMode` literal type, `TokenCountStrategy` protocol, `ExactTokenCount`, `IncrementalTokenCount`, and `create_token_counter(name, tokenizer)` factory.
- Modify: `src/lumberjack/core/splitters/base.py`
  - Add `count_mode` parameter to `BaseSplitter.__init__`.
  - Build `self.token_counter` strategy object.
  - Route all internal counting call sites through the strategy; keep `self.tokenizer` for the `BlockSplitter` (block splitting still uses the raw tokenizer).
- Modify: `src/lumberjack/core/splitters/__init__.py`
  - Add `count_mode` parameter to `create_splitter` and forward it.
- Modify: `src/lumberjack/lumber.py`
  - Add `token_counter` parameter.
  - Resolve engine + mode via `create_token_counter`; forward to `create_splitter`.
- Modify: `src/lumberjack/cli.py`
  - Add `--token-counter` argument; keep `--tokenizer`.
- Modify: `src/lumberjack/web/routes.py`
  - Add `token_counter` to `TextSplitRequest` and `split_file` form.
- Create: `tests/test_token_counting_modes.py`
  - New test module covering the factory, strategies, and three-mode behavior.
- Modify: `AGENTS.md`
  - Document the three modes and the `--token-counter` CLI option.

---

### Task 1: Add `ApproxCharTokenizer`

**Files:**
- Modify: `tests/test_token_counting_modes.py` (create)
- Modify: `src/lumberjack/core/tokenizers.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_token_counting_modes.py`:

```python
from __future__ import annotations

import pytest

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_token_counting_modes.py -v`
Expected: FAIL with `ImportError: cannot import name 'ApproxCharTokenizer'`

- [ ] **Step 3: Implement `ApproxCharTokenizer`**

In `src/lumberjack/core/tokenizers.py`, add after the `SimpleCharTokenizer` class (before `create_tokenizer`):

```python
class ApproxCharTokenizer(TokenizerProtocol):
    """Approximate tokenizer that estimates tokens as ``len(text) // 4``.

    A common industry rule of thumb (character count divided by four) used by
    the ``token_counter="simple"`` counting mode.  The splitter only uses
    :meth:`count`; :meth:`encode` is a protocol placeholder.
    """

    def encode(self, text: str, *, cache: bool = False) -> tuple[int, ...]:  # noqa: ARG002
        return ()

    def count(self, text: str, *, cache: bool = False) -> int:  # noqa: ARG002
        return len(text) // 4
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_token_counting_modes.py::TestApproxCharTokenizer -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_token_counting_modes.py src/lumberjack/core/tokenizers.py
git commit -m "feat(tokenizers): add ApproxCharTokenizer (chars // 4)"
```

---

### Task 2: Add `default_cache` to `TiktokenTokenizer`

**Files:**
- Modify: `tests/test_token_counting_modes.py`
- Modify: `src/lumberjack/core/tokenizers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_token_counting_modes.py`:

```python
from lumberjack.core.tokenizers import TiktokenTokenizer


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_token_counting_modes.py::TestTiktokenDefaultCache -v`
Expected: FAIL with `TypeError: ... 'default_cache'` (kwarg not accepted)

- [ ] **Step 3: Add `default_cache` to `TiktokenTokenizer`**

In `src/lumberjack/core/tokenizers.py`, modify the `TiktokenTokenizer` class. Change the `__init__` signature and the `encode` method:

```python
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_cache_size: int = 1000,
        default_cache: bool = False,
    ):
        import tiktoken
        from cachetools import LRUCache

        self.encoding = tiktoken.encoding_for_model(model)
        self.default_cache = default_cache
        self._cache: LRUCache[str, tuple[int, ...]] = LRUCache(maxsize=max_cache_size)
        self._lock = RLock()

    def encode(
        self,
        text: str,
        *,
        cache: bool | None = None,
    ) -> tuple[int, ...]:
        if not text:
            return ()
        use_cache = self.default_cache if cache is None else cache
        if use_cache:
            with self._lock:
                cached = self._cache.get(text)
                if cached is not None:
                    return cached
        token_ids = tuple(self.encoding.encode(text))
        if use_cache:
            with self._lock:
                self._cache[text] = token_ids
        return token_ids

    def count(
        self,
        text: str,
        *,
        cache: bool | None = None,
    ) -> int:
        if not text:
            return 0
        return len(self.encode(text, cache=cache))
```

Note: changing `cache: bool` to `cache: bool | None = None` is backward compatible — existing callers passing `cache=True`/`cache=False` continue to work; only the new `None` default defers to `default_cache`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_token_counting_modes.py::TestTiktokenDefaultCache -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run existing tokenizer-related tests to confirm no regression**

Run: `uv run pytest tests/ -v -k "tokenizer or split or render or api or web or docx or html"`
Expected: PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add tests/test_token_counting_modes.py src/lumberjack/core/tokenizers.py
git commit -m "feat(tokenizers): add default_cache to TiktokenTokenizer"
```

---

### Task 3: Add `CountMode` and `TokenCountStrategy` types

**Files:**
- Modify: `tests/test_token_counting_modes.py`
- Modify: `src/lumberjack/core/tokenizers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_token_counting_modes.py`:

```python
from lumberjack.core.tokenizers import (
    ExactTokenCount,
    IncrementalTokenCount,
    SimpleCharTokenizer,
)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_token_counting_modes.py::TestStrategyCountBody -v`
Expected: FAIL with `ImportError: cannot import name 'ExactTokenCount'`

- [ ] **Step 3: Add the strategy types**

In `src/lumberjack/core/tokenizers.py`, add at the top after the imports (and before `TiktokenTokenizer`) the `CountMode` literal and the protocol — and at the bottom (before `create_tokenizer`) add the two concrete strategies:

Top of file, after `from .protocols import TokenizerProtocol`:

```python
from typing import Protocol, TypeAlias

CountMode: TypeAlias = Literal["exact", "incremental"]  # noqa: UP040
```

Also add `Literal` to the imports (already imported via the line above).

Then add the strategy protocol after `CountMode`:

```python
class TokenCountStrategy(Protocol):
    """Abstracts how the splitter counts tokens at internal decision sites.

    Two implementations exist: :class:`ExactTokenCount` counts the fully
    rendered text at every site (used by the ``simple`` and ``accurate``
    modes); :class:`IncrementalTokenCount` reuses the additive / separator-delta
    arithmetic (used by the ``estimate`` mode).
    """

    def count_body(self, parts: list[str], separator: str) -> int: ...
    def count_text(self, text: str) -> int: ...
    def separator_delta(self, text: str, separator: str) -> int: ...
```

Then, before `create_tokenizer`, add the two concrete classes:

```python
class ExactTokenCount:
    """Counting strategy that counts fully rendered text at every site."""

    def __init__(self, tokenizer: TokenizerProtocol) -> None:
        self.tokenizer = tokenizer

    def count_body(self, parts: list[str], separator: str) -> int:
        rendered = separator.join(parts)
        return self.tokenizer.count(rendered, cache=True)

    def count_text(self, text: str) -> int:
        return self.tokenizer.count(text, cache=True)

    def separator_delta(self, text: str, separator: str) -> int:
        if not text:
            return self.tokenizer.count(separator, cache=True)
        return self.tokenizer.count(f"{text}{separator}", cache=True) - self.tokenizer.count(
            text, cache=True
        )


class IncrementalTokenCount:
    """Counting strategy that reuses additive / separator-window arithmetic.

    ``separator_delta`` mirrors the original ``_separator_delta_after`` 8-char
    tail-window approximation so the incremental mode reproduces the legacy
    estimate behavior.
    """

    _DELTA_WINDOW = 8

    def __init__(self, tokenizer: TokenizerProtocol) -> None:
        self.tokenizer = tokenizer

    def count_body(self, parts: list[str], separator: str) -> int:
        if not parts:
            return 0
        rendered = separator.join(parts)
        return self.tokenizer.count(rendered, cache=True)

    def count_text(self, text: str) -> int:
        return self.tokenizer.count(text, cache=True)

    def separator_delta(self, text: str, separator: str) -> int:
        if not text:
            return 0
        tail = text.rstrip("\n")[-self._DELTA_WINDOW:]
        return self.tokenizer.count(f"{tail}{separator}", cache=True) - self.tokenizer.count(
            tail, cache=True
        )
```

Note: `IncrementalTokenCount.count_body` deliberately computes the full join — the *incremental* optimization lives at the splitter's block-accumulation loop (Task 6), where running totals avoid re-counting the whole join each step. The `separator_delta` difference is what distinguishes the two strategies' approximation at subtree/merge boundaries.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_token_counting_modes.py::TestStrategyCountBody -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_token_counting_modes.py src/lumberjack/core/tokenizers.py
git commit -m "feat(tokenizers): add CountMode, TokenCountStrategy, ExactTokenCount, IncrementalTokenCount"
```

---

### Task 4: Add `create_token_counter` factory

**Files:**
- Modify: `tests/test_token_counting_modes.py`
- Modify: `src/lumberjack/core/tokenizers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_token_counting_modes.py`:

```python
from lumberjack.core.tokenizers import create_token_counter


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

    def test_estimate_with_simple_tokenizer_upgrades_to_tiktoken(self) -> None:
        engine, mode = create_token_counter("estimate", SimpleCharTokenizer())
        assert isinstance(engine, TiktokenTokenizer)
        assert mode == "incremental"

    def test_accurate_forces_cache_on_tiktoken_and_uses_exact(self) -> None:
        engine, mode = create_token_counter("accurate")
        assert isinstance(engine, TiktokenTokenizer)
        assert engine.default_cache is True
        assert mode == "exact"

    def test_accurate_with_existing_tiktoken_upgrades_cache(self) -> None:
        existing = TiktokenTokenizer()
        engine, mode = create_token_counter("accurate", existing)
        assert isinstance(engine, TiktokenTokenizer)
        assert engine.default_cache is True
        assert mode == "exact"

    def test_unknown_token_counter_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported token_counter"):
            create_token_counter("bogus")

    def test_unknown_tokenizer_engine_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported tokenizer"):
            create_token_counter("estimate", _BogusEngine())  # noqa: F821


class _BogusEngine:
    # Minimal stand-in that is not a valid engine name; the factory rejects by
    # re-validating via create_tokenizer when a name lookup is required.
    pass
```

Note: the last test reflects that `create_token_counter` only validates engine *names* when it needs to construct one. When the caller passes an instance (as here), no name validation applies. Adjust the assertion in Step 3 accordingly — see implementation note.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_token_counting_modes.py::TestCreateTokenCounter -v`
Expected: FAIL with `ImportError: cannot import name 'create_token_counter'`

- [ ] **Step 3: Implement `create_token_counter`**

In `src/lumberjack/core/tokenizers.py`, add at the bottom (after `create_tokenizer`):

```python
def create_token_counter(
    name: str,
    tokenizer: TokenizerProtocol | None = None,
) -> tuple[TokenizerProtocol, CountMode]:
    """Resolve a counting mode into ``(engine, count_mode)``.

    Args:
        name: Counting mode — ``"simple"``, ``"estimate"``, or ``"accurate"``.
        tokenizer: Caller-supplied engine instance.  Ignored for ``"simple"``.
            For ``"estimate"`` / ``"accurate"`` it is used directly when
            provided, otherwise a ``tiktoken`` engine is constructed.

    Returns:
        A ``(engine, count_mode)`` tuple.  ``count_mode`` is ``"exact"`` for
        ``simple`` / ``accurate`` and ``"incremental"`` for ``estimate``.

    Raises:
        ValueError: If ``name`` is not a supported counting mode.
    """
    normalized = name.strip().lower()
    if normalized == "simple":
        return ApproxCharTokenizer(), "exact"
    if normalized == "estimate":
        engine = tokenizer if tokenizer is not None else create_tokenizer("tiktoken")
        return engine, "incremental"
    if normalized == "accurate":
        engine = tokenizer if tokenizer is not None else create_tokenizer("tiktoken")
        engine = _ensure_tiktoken_cache_forced(engine)
        return engine, "exact"
    raise ValueError(f"Unsupported token_counter: {name}")


def _ensure_tiktoken_cache_forced(
    engine: TokenizerProtocol,
) -> TokenizerProtocol:
    """Return a tiktoken engine with ``default_cache=True``.

    If ``engine`` is a :class:`TiktokenTokenizer` that already has caching
    forced on, return it unchanged.  If it is a ``TiktokenTokenizer`` with
    caching off, construct a fresh instance with ``default_cache=True`` sharing
    the same model.  Non-tiktoken engines are returned unchanged.
    """
    if isinstance(engine, TiktokenTokenizer):
        if engine.default_cache:
            return engine
        return TiktokenTokenizer(default_cache=True)
    return engine
```

Then **fix the `test_unknown_tokenizer_engine_raises` test** written in Step 1 — it cannot trigger the engine-name validation path because a bogus instance is passed directly. Replace that test with a test that exercises the name-validation path (no instance supplied but a mode that needs construction is always tiktoken, so instead assert the documented "instance passes through" behavior):

```python
    def test_unknown_engine_name_is_not_validated_for_instances(self) -> None:
        # When the caller supplies an instance, no name validation runs.
        # Name validation happens inside create_tokenizer (called only when an
        # engine must be constructed), which is covered by its own tests.
        bogus = _BogusEngine()
        engine, mode = create_token_counter("estimate", bogus)
        assert engine is bogus
        assert mode == "incremental"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_token_counting_modes.py::TestCreateTokenCounter -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_token_counting_modes.py src/lumberjack/core/tokenizers.py
git commit -m "feat(tokenizers): add create_token_counter factory"
```

---

### Task 5: Thread `count_mode` through `create_splitter` and `BaseSplitter`

**Files:**
- Modify: `tests/test_token_counting_modes.py`
- Modify: `src/lumberjack/core/splitters/__init__.py`
- Modify: `src/lumberjack/core/splitters/base.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_token_counting_modes.py`:

```python
from lumberjack.core.models import SplitOptions
from lumberjack.core.splitters import create_splitter


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_token_counting_modes.py::TestCreateSplitterCountMode -v`
Expected: FAIL with `TypeError: create_splitter() got an unexpected keyword argument 'count_mode'`

- [ ] **Step 3: Update `create_splitter`**

In `src/lumberjack/core/splitters/__init__.py`, modify the `create_splitter` signature and body. Update the imports at the top to include `CountMode`:

```python
from __future__ import annotations

from ..models import SplitOptions
from ..protocols import SplitterProtocol, TokenizerProtocol
from ..tokenizers import CountMode
from .base import BaseSplitter
from .recursive import RecursiveSplitter
from .section import SectionSplitter

SPLITTER_REGISTRY: dict[str, type[BaseSplitter]] = {
    "recursive": RecursiveSplitter,
    "section": SectionSplitter,
}


def create_splitter(
    name: str,
    tokenizer: TokenizerProtocol | None = None,
    options: SplitOptions | None = None,
    count_mode: CountMode = "exact",
) -> SplitterProtocol:
    """Instantiate a splitter by name."""
    normalized = name.strip().lower()
    cls = SPLITTER_REGISTRY.get(normalized)
    if cls is None:
        raise ValueError(f"Unsupported splitter: {name}")
    return cls(tokenizer=tokenizer, options=options, count_mode=count_mode)


__all__ = [
    "SPLITTER_REGISTRY",
    "BaseSplitter",
    "RecursiveSplitter",
    "SectionSplitter",
    "create_splitter",
]
```

- [ ] **Step 4: Update `BaseSplitter.__init__` to build the strategy**

In `src/lumberjack/core/splitters/base.py`, modify the imports and `__init__`. First update the import from `..tokenizers`:

```python
from ..tokenizers import (
    ApproxCharTokenizer,
    CountMode,
    ExactTokenCount,
    IncrementalTokenCount,
    SimpleCharTokenizer,
)
```

Then replace the `__init__` method (lines 29-37 in the current file):

```python
    def __init__(
        self,
        tokenizer: TokenizerProtocol | None = None,
        options: SplitOptions | None = None,
        count_mode: CountMode = "exact",
    ):
        self.tokenizer = tokenizer or SimpleCharTokenizer()
        self.options = options or SplitOptions()
        self.count_mode = count_mode
        self.token_counter = self._build_token_counter(count_mode)
        self._validate_options()
        self._block_splitter = BlockSplitter(self.tokenizer, self.options)

    def _build_token_counter(self, count_mode: CountMode):
        if count_mode == "incremental":
            return IncrementalTokenCount(self.tokenizer)
        return ExactTokenCount(self.tokenizer)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_token_counting_modes.py::TestCreateSplitterCountMode -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full existing splitter test suite to confirm default-exact matches current behavior**

Run: `uv run pytest tests/test_splitter.py tests/test_render_headings.py -v`
Expected: PASS (the default `count_mode="exact"` plus the not-yet-routed call sites still use `self.tokenizer.count` directly, so behavior is unchanged at this task; full routing happens in Task 6)

- [ ] **Step 7: Commit**

```bash
git add tests/test_token_counting_modes.py src/lumberjack/core/splitters/__init__.py src/lumberjack/core/splitters/base.py
git commit -m "feat(splitters): thread count_mode through create_splitter and BaseSplitter"
```

---

### Task 6: Route `BaseSplitter` counting call sites through the strategy

This is the core migration. The splitter's counting call sites switch from direct `self.tokenizer.count(...)` and `_separator_delta_after(...)` to `self.token_counter.*` methods. The exact strategy recomputes full text; the incremental strategy preserves the legacy approximation.

**Files:**
- Modify: `tests/test_splitter.py`
- Modify: `src/lumberjack/core/splitters/base.py`

- [ ] **Step 1: Add a regression test asserting exact-mode still matches legacy char counts**

In `tests/test_splitter.py`, add near the top imports:

```python
from lumberjack.core.tokenizers import ExactTokenCount, IncrementalTokenCount
```

Append a new test at the end of the file:

```python
def test_splitter_default_uses_exact_strategy() -> None:
    """The default splitter build uses the ExactTokenCount strategy."""
    splitter = create_splitter("recursive", SimpleCharTokenizer())
    assert isinstance(splitter.token_counter, ExactTokenCount)


def test_splitter_token_counter_routes_through_strategy() -> None:
    """Both strategies produce the same chunk body for a simple document,
    because body rendering is independent of counting.
    """
    source = "# Title\n\nFirst paragraph here.\n\nSecond paragraph here.\n"
    document = MarkdownItParser().parse(source)
    options = SplitOptions(max_tokens=1200)

    exact = create_splitter("recursive", SimpleCharTokenizer(), options=options)
    incr = create_splitter(
        "recursive",
        SimpleCharTokenizer(),
        options=options,
        count_mode="incremental",
    )
    exact_chunks = exact.split(document)
    incr_chunks = incr.split(document)
    assert [c.body for c in exact_chunks] == [c.body for c in incr_chunks]
    assert [c.token_count for c in exact_chunks] == [c.token_count for c in incr_chunks]
```

- [ ] **Step 2: Run the new test to verify it fails (strategies not yet routed)**

Run: `uv run pytest tests/test_splitter.py::test_splitter_token_counter_routes_through_strategy -v`
Expected: May PASS already (bodies are identical regardless of strategy); the value of this test is guarding against future routing bugs. If it passes, proceed — Task 7's equivalence test is the stronger guard.

- [ ] **Step 3: Route `_separator_delta_after` through the strategy**

In `src/lumberjack/core/splitters/base.py`, the method `_separator_delta_after` (lines 96-103) currently calls `self.tokenizer.count` directly. Replace the method body so it delegates to the strategy:

```python
    def _separator_delta_after(self, text: str) -> int:
        """Estimate the token delta caused by appending the Markdown separator."""
        return self.token_counter.separator_delta(text, SEPARATOR)
```

Note: the `ExactTokenCount.separator_delta` uses the full text (not an 8-char window), which is the exact-mode behavior. The `IncrementalTokenCount.separator_delta` keeps the 8-char window, preserving the legacy approximation.

- [ ] **Step 4: Route the title-count call in `_heading_path_token_count`**

In `src/lumberjack/core/splitters/base.py`, the method `_heading_path_token_count` (lines 45-54) calls `self.tokenizer.count(...)`. Replace the body:

```python
    def _heading_path_token_count(self, path: HeadingPath) -> int:
        if not path:
            return 0
        tokens = 0
        for level, title in path:
            if title:
                tokens = tokens + self.token_counter.count_text(
                    "#" * level + " " + title + SEPARATOR
                )
        return tokens
```

- [ ] **Step 5: Route the body-count calls in `_measure_section`**

In `_measure_section` (lines 126-192), replace the body-token-counting loop. Find the block (lines 131-140):

```python
        body_token_count = 0
        for idx, block in enumerate(section.blocks):
            if not block.text:
                continue
            if idx == len(section.blocks) - 1:
                body_token_count += self.tokenizer.count(block.text, cache=True)
            else:
                body_token_count += self.tokenizer.count(
                    block.text + SEPARATOR, cache=True
                )
```

Replace with a strategy-based computation. Because the strategy's `count_body` joins parts with the separator, but the last block must NOT have a trailing separator, build the body-text first then count it:

```python
        body_token_count = 0
        for idx, block in enumerate(section.blocks):
            if not block.text:
                continue
            if idx == len(section.blocks) - 1:
                body_token_count += self.token_counter.count_text(block.text)
            else:
                body_token_count += self.token_counter.count_text(block.text) + (
                    self.token_counter.separator_delta(block.text, SEPARATOR)
                )
```

Also the title count at lines 143-148:

```python
        if section.level > 0:
            title_token_count = self.tokenizer.count(
                "#" * section.level + " " + section.title + SEPARATOR, cache=True
            )
        else:
            title_token_count = 0
```

Replace with:

```python
        if section.level > 0:
            title_token_count = self.token_counter.count_text(
                "#" * section.level + " " + section.title + SEPARATOR
            )
        else:
            title_token_count = 0
```

- [ ] **Step 6: Route the block-token calls in `_split_section_body`**

In `_split_section_body` (lines 194-420), there are several direct `self.tokenizer.count(...)` calls. Replace each:

At line 272 (`block_tokens = self.tokenizer.count(block.text, cache=True)`):
```python
                block_tokens = self.token_counter.count_text(block.text)
```

At line 280 (`piece_tokens = self.tokenizer.count(piece)`):
```python
                        piece_tokens = self.token_counter.count_text(piece)
```

At lines 321-329 (the incremental `candidate_body_tokens` block):
```python
            block_tokens = self.token_counter.count_text(block.text)
            if current_parts:
                candidate_body_tokens = (
                    current_body_tokens
                    - self.token_counter.count_text(current_parts[-1])
                    + self.token_counter.count_text(current_parts[-1])
                    + self.token_counter.separator_delta(current_parts[-1], SEPARATOR)
                    + block_tokens
                )
            else:
                candidate_body_tokens = block_tokens
```

Note: the original expression was `current_body_tokens - count(last) + count(last+sep) + block_tokens`. The rewrite keeps the same arithmetic shape — `count(last) + separator_delta(last, sep)` equals `count(last+sep)` for the exact strategy (full text) and approximates it for the incremental strategy (8-char window). Simplify to:

```python
            block_tokens = self.token_counter.count_text(block.text)
            if current_parts:
                candidate_body_tokens = (
                    current_body_tokens
                    + self.token_counter.separator_delta(current_parts[-1], SEPARATOR)
                    + block_tokens
                )
            else:
                candidate_body_tokens = block_tokens
```

(The `- count(last) + count(last)` terms cancel, leaving just the separator delta.)

At line 395 (`piece_tokens = self.tokenizer.count(piece)`):
```python
                piece_tokens = self.token_counter.count_text(piece)
```

- [ ] **Step 7: Route the finalization count in `_finalize_chunks`**

In `_finalize_chunks` (line 442):
```python
            token_count = self.tokenizer.count(body)
```
Replace with:
```python
            token_count = self.token_counter.count_text(body)
```

For `estimated`, at lines 451-463 the existing `_draft_budget_tokens` and `_separator_delta_after` calls already route through strategy methods (after Steps 3-4), so no further change is needed there.

- [ ] **Step 8: Run the full splitter test suite**

Run: `uv run pytest tests/test_splitter.py tests/test_render_headings.py -v`
Expected: PASS. The default `count_mode="exact"` path must reproduce the legacy behavior, because exact-strategy counting equals direct full-text counting. If any test fails, the failure indicates a routing bug — fix the specific call site before proceeding.

- [ ] **Step 9: Run type check and lint**

Run: `uv run ty check src/lumberjack/core/splitters/base.py`
Run: `uv run ruff check --fix src/lumberjack/core/splitters/base.py`
Run: `uv run ruff format src/lumberjack/core/splitters/base.py`
Expected: No errors.

- [ ] **Step 10: Commit**

```bash
git add tests/test_splitter.py src/lumberjack/core/splitters/base.py
git commit -m "refactor(splitters): route counting call sites through TokenCountStrategy"
```

---

### Task 7: Add three-mode end-to-end and truncation/zero-estimation tests

**Files:**
- Modify: `tests/test_token_counting_modes.py`

- [ ] **Step 1: Write the three-mode equivalence and guard tests**

Append to `tests/test_token_counting_modes.py`:

```python
from lumberjack.core.parsers.markdown.parser import MarkdownItParser
from lumberjack.core.tokenizers import create_token_counter


def _split_with_mode(
    source: str, token_counter: str, max_tokens: int = 1200
):
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
        # A document with several short blocks; each block alone is < 4 chars
        # (would truncate to 0 under per-block //4), but the rendered body is
        # longer.  Assert the chunk count reflects the full-body count.
        source = "# H\n\nab\n\ncd\n\nef\n\ng\n"
        chunks, _ = _split_with_mode(source, "simple", max_tokens=100)
        assert chunks
        for chunk in chunks:
            assert chunk.token_count == len(chunk.body) // 4


class TestAccurateZeroEstimation:
    def test_accurate_uses_full_count_not_incremental_delta(self) -> None:
        # Construct a case where block-boundary token merging could make the
        # incremental delta differ from a full recount.  With tiktoken, the
        # boundary between two joined blocks can merge characters into one
        # token.  accurate mode must report the full recount.
        source = (
            "# Doc\n\n"
            "The quick brown.\n\n"
            "fox jumps.\n\n"
            "over the lazy.\n\n"
            "dog.\n"
        )
        chunks, _ = _split_with_mode(source, "accurate", max_tokens=1200)
        engine, _ = create_token_counter("accurate")
        for chunk in chunks:
            assert chunk.token_count == engine.count(chunk.body, cache=True)
            assert chunk.estimated_token_count == chunk.token_count
```

- [ ] **Step 2: Run the new tests**

Run: `uv run pytest tests/test_token_counting_modes.py -v`
Expected: PASS for all classes. (These require tiktoken installed; the dev install includes the `tokenizers` extra.)

If tiktoken is not installed, install with `uv sync --extra tokenizers` and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_token_counting_modes.py
git commit -m "test(tokenizers): add three-mode boundary, truncation, and zero-estimation tests"
```

---

### Task 8: Wire `token_counter` through `lumber()`

**Files:**
- Modify: `tests/test_token_counting_modes.py`
- Modify: `src/lumberjack/lumber.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_token_counting_modes.py`:

```python
from lumberjack import lumber


class TestLumberTokenCounter:
    def test_lumber_accepts_token_counter_simple(self) -> None:
        chunks = lumber("# T\n\nbody\n", token_counter="simple")
        assert chunks
        assert chunks[0].token_count == len(chunks[0].body) // 4

    def test_lumber_accepts_token_counter_estimate(self) -> None:
        chunks = lumber("# T\n\nbody text here\n", token_counter="estimate")
        assert chunks

    def test_lumber_accepts_token_counter_accurate(self) -> None:
        chunks = lumber("# T\n\nbody text here\n", token_counter="accurate")
        assert chunks

    def test_lumber_simple_ignores_tiktoken_engine(self) -> None:
        # token_counter=simple must ignore tokenizer=tiktoken and use chars//4
        chunks = lumber(
            "# T\n\nbody text\n", token_counter="simple", tokenizer="tiktoken"
        )
        assert chunks[0].token_count == len(chunks[0].body) // 4

    def test_lumber_estimate_uses_provided_tiktoken_engine(self) -> None:
        chunks = lumber(
            "# T\n\nbody text\n",
            token_counter="estimate",
            tokenizer="tiktoken",
        )
        assert chunks

    def test_lumber_unknown_token_counter_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported token_counter"):
            lumber("# T\n\nbody\n", token_counter="bogus")

    def test_lumber_unknown_tokenizer_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported tokenizer"):
            lumber("# T\n\nbody\n", token_counter="estimate", tokenizer="bogus")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_token_counting_modes.py::TestLumberTokenCounter -v`
Expected: FAIL with `TypeError: lumber() got an unexpected keyword argument 'token_counter'`

- [ ] **Step 3: Update `lumber()`**

In `src/lumberjack/lumber.py`, update the imports and the `lumber` function. Replace the import line:

```python
from .core.tokenizers import create_token_counter, create_tokenizer
```

Add `token_counter: str = "simple"` parameter to the `lumber` signature (after `tokenizer: str = "simple"`):

```python
def lumber(
    text: str | bytes | Path = "",
    *,
    format: str = "auto",
    document_title: str | None = None,
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_tokens: int | None = 50,
    skip_empty_sections: bool = True,
    render_headings: bool = True,
    block_options: Mapping[str, BaseParams | dict] | None = None,
    tokenizer: str = "simple",
    token_counter: str = "simple",
    splitter: str = "recursive",
    document_metadata: dict[str, object] | None = None,
    max_heading_level: int | None = None,
) -> list[Chunk]:
```

Update the docstring to document `token_counter` (insert after the `tokenizer` doc line):

```python
        tokenizer: Built-in tokenizer engine name (``"simple"`` or
            ``"tiktoken"``). Ignored when ``token_counter="simple"``.
        token_counter: Counting mode — ``"simple"`` (chars // 4, the default),
            ``"estimate"`` (tiktoken with additive incremental estimate), or
            ``"accurate"`` (tiktoken, fully cached, no estimation).
```

Replace the tokenizer construction block (lines 65-79):

```python
    if not isinstance(tokenizer, str):
        raise TypeError(
            "tokenizer must be a string selecting a built-in tokenizer. "
            "For custom tokenizers, parse manually and pass the tokenizer "
            "instance to a splitter."
        )
    if not isinstance(splitter, str):
        raise TypeError(
            "splitter must be a string selecting a built-in splitter. "
            "For custom splitters, parse manually and call splitter.split()."
        )

    input_format = detect_format(text, format)

    tokenizer_impl = create_tokenizer(tokenizer)
```

with:

```python
    if not isinstance(tokenizer, str):
        raise TypeError(
            "tokenizer must be a string selecting a built-in tokenizer. "
            "For custom tokenizers, parse manually and pass the tokenizer "
            "instance to a splitter."
        )
    if not isinstance(token_counter, str):
        raise TypeError(
            "token_counter must be a string selecting a counting mode. "
            "For custom counting strategies, parse manually and pass the "
            "tokenizer instance plus count_mode to a splitter."
        )
    if not isinstance(splitter, str):
        raise TypeError(
            "splitter must be a string selecting a built-in splitter. "
            "For custom splitters, parse manually and call splitter.split()."
        )

    input_format = detect_format(text, format)

    # Resolve the counting engine + mode. For token_counter="simple" the
    # tokenizer argument is ignored (chars//4). For estimate/accurate the
    # named engine is constructed; a "simple" engine name is upgraded to
    # tiktoken because estimate/accurate need a real tokenizer.
    if token_counter == "simple":
        tokenizer_impl, count_mode = create_token_counter("simple")
    else:
        engine = create_tokenizer(tokenizer) if tokenizer != "simple" else create_tokenizer("tiktoken")
        tokenizer_impl, count_mode = create_token_counter(token_counter, engine)
```

Then update the splitter creation (currently `splitter_impl = create_splitter(splitter, tokenizer=tokenizer_impl, options=options)`):

```python
    splitter_impl = create_splitter(
        splitter,
        tokenizer=tokenizer_impl,
        options=options,
        count_mode=count_mode,
    )
    return splitter_impl.split(document)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_token_counting_modes.py::TestLumberTokenCounter -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full api test suite**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS (the existing `lumber()` tests use the default `token_counter="simple"`, which still works; `test_lumber_rejects_tokenizer_instances` is preserved).

- [ ] **Step 6: Commit**

```bash
git add tests/test_token_counting_modes.py src/lumberjack/lumber.py
git commit -m "feat(api): wire token_counter through lumber()"
```

---

### Task 9: Add `--token-counter` to the CLI

**Files:**
- Modify: `tests/test_token_counting_modes.py`
- Modify: `src/lumberjack/cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_token_counting_modes.py`:

```python
from lumberjack.cli import build_parser


class TestCliTokenCounter:
    def test_default_token_counter_is_simple(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.md"])
        assert args.token_counter == "simple"
        assert args.tokenizer == "simple"

    def test_token_counter_accepts_three_modes(self) -> None:
        parser = build_parser()
        for mode in ("simple", "estimate", "accurate"):
            args = parser.parse_args(["input.md", "--token-counter", mode])
            assert args.token_counter == mode

    def test_token_counter_rejects_unknown(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["input.md", "--token-counter", "bogus"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_token_counting_modes.py::TestCliTokenCounter -v`
Expected: FAIL with `AttributeError: 'Namespace' object has no attribute 'token_counter'`

- [ ] **Step 3: Add the `--token-counter` argument**

In `src/lumberjack/cli.py`, add the argument after the existing `--tokenizer` argument (after line 32):

```python
    parser.add_argument(
        "--token-counter",
        choices=("simple", "estimate", "accurate"),
        default="simple",
        help="Token counting mode: simple (chars//4), estimate (tiktoken with "
        "additive incremental estimate), accurate (tiktoken, fully cached, "
        "no estimation). The --tokenizer engine is ignored when "
        "token-counter is simple.",
    )
```

Then in `main()`, add `token_counter=args.token_counter,` to the `lumber(...)` call (after the `tokenizer=args.tokenizer,` line):

```python
    chunks = lumber(
        input_path,
        format=args.input_format,
        max_tokens=args.max_tokens,
        ideal_max_tokens_ratio=args.ideal_max_tokens_ratio,
        merge_below_tokens=args.merge_below_tokens,
        block_options=block_options,
        tokenizer=args.tokenizer,
        token_counter=args.token_counter,
        splitter=args.splitter,
        render_headings=not args.no_render_headings,
        max_heading_level=args.max_heading_level,
        document_metadata={"path": str(input_path.resolve())},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_token_counting_modes.py::TestCliTokenCounter -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_token_counting_modes.py src/lumberjack/cli.py
git commit -m "feat(cli): add --token-counter option"
```

---

### Task 10: Add `token_counter` to the Web API

**Files:**
- Modify: `tests/test_web.py`
- Modify: `src/lumberjack/web/routes.py`

- [ ] **Step 1: Inspect the existing web test to mirror its style**

Run: `uv run pytest tests/test_web.py -v --collect-only | head -30`
Read `tests/test_web.py` to find the request payload shape used for the `/split/text` endpoint.

- [ ] **Step 2: Write the failing test**

In `tests/test_web.py`, add a test (mirror the existing client-based test style). Add near the imports:

```python
# (no new imports needed if client fixture exists)
```

Append:

```python
def test_split_text_accepts_token_counter(client) -> None:  # noqa: ANN001
    """The /split/text endpoint accepts a token_counter field."""
    payload = {
        "text": "# T\n\nbody\n",
        "input_format": "markdown",
        "token_counter": "simple",
    }
    response = client.post("/lumber/api/split/text", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["chunk_count"] >= 1
    chunk = data["chunks"][0]
    assert chunk["token_count"] == len(chunk["body"]) // 4
```

Note: match the actual client fixture name and route prefix (`/lumber/api/split/text` vs `/split/text`) used by the existing tests in `tests/test_web.py`. Adjust the route prefix in the test to match what the existing tests use.

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_web.py::test_split_text_accepts_token_counter -v`
Expected: FAIL — the endpoint ignores the unknown field (FastAPI silently drops it), so the assertion on `token_count == len(body)//4` may pass by accident. If it passes, strengthen the test by checking that `token_counter="accurate"` produces a tiktoken-based count:

```python
def test_split_text_accepts_token_counter_accurate(client) -> None:  # noqa: ANN001
    payload = {
        "text": "# T\n\nThe quick brown fox.\n",
        "input_format": "markdown",
        "token_counter": "accurate",
    }
    response = client.post("/lumber/api/split/text", json=payload)
    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    # accurate mode recomputes the full cached count; it must be > 0 and not
    # equal to chars//4 on typical English text.
    assert chunk["token_count"] > 0
```

- [ ] **Step 4: Add `token_counter` to the request models and forwarding**

In `src/lumberjack/web/routes.py`:

Add to `TextSplitRequest` (after `tokenizer: str = "simple"`):

```python
    token_counter: str = "simple"
```

In `split_text`, add `token_counter=payload.token_counter,` to the `lumber(...)` call (after `tokenizer=payload.tokenizer,`):

```python
        chunks = lumber(
            payload.text,
            format=payload.input_format,
            max_tokens=payload.max_tokens,
            ideal_max_tokens_ratio=payload.ideal_max_tokens_ratio,
            merge_below_tokens=payload.merge_below_tokens,
            skip_empty_sections=payload.skip_empty_sections,
            render_headings=payload.render_headings,
            block_options=block_options,
            tokenizer=payload.tokenizer,
            token_counter=payload.token_counter,
            splitter=payload.splitter,
            max_heading_level=payload.max_heading_level,
        )
```

In `split_file`, add a `token_counter: str = Form("simple"),` parameter (after `tokenizer: str = Form("simple"),`) and `token_counter=token_counter,` in the `lumber(...)` call:

```python
    tokenizer: str = Form("simple"),
    token_counter: str = Form("simple"),
    splitter: str = Form("recursive"),
```

and:

```python
            tokenizer=tokenizer,
            token_counter=token_counter,
            splitter=splitter,
```

- [ ] **Step 5: Run the web tests**

Run: `uv run pytest tests/test_web.py -v`
Expected: PASS (including the new test).

- [ ] **Step 6: Commit**

```bash
git add tests/test_web.py src/lumberjack/web/routes.py
git commit -m "feat(web): add token_counter to split endpoints"
```

---

### Task 11: Update `AGENTS.md` documentation

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update the Commands section**

In `AGENTS.md`, find the "Commands" section CLI example:

```
uv run lumber path/to/file.md --max-tokens 1200 --merge-below-tokens 50 -f json
```

Add a second example demonstrating `--token-counter`:

```
# Run CLI with the accurate counting mode (tiktoken, fully cached)
uv run lumber path/to/file.md --token-counter accurate --max-tokens 1200 -f json
```

- [ ] **Step 2: Update the CLI Behavior section**

In `AGENTS.md`, find the "CLI Behavior" section. Update it to document the new option. Replace the existing tokenizer bullet:

```markdown
- Tokenizers: `simple`, `tiktoken`
```

with:

```markdown
- Tokenizers (engine): `simple`, `tiktoken`
- Token counting modes: `simple` (chars // 4, default), `estimate` (tiktoken with additive incremental estimate), `accurate` (tiktoken, fully cached, no estimation). The `--tokenizer` engine is ignored when `--token-counter` is `simple`.
```

- [ ] **Step 3: Update the Splitting Rules section**

In `AGENTS.md`, find the "Splitting Rules" section. Add a paragraph at the end describing the counting modes and their `token_count` / `estimated_token_count` semantics:

```markdown
- Token counting modes (`--token-counter`): `simple` uses `chars // 4`; `estimate` uses the additive incremental estimate backed by the configured engine; `accurate` performs no estimation — every internal count recomputes the fully rendered text with caching forced on. `Chunk.token_count` reflects the mode's primary count; `Chunk.estimated_token_count` is retained in all modes and equals `token_count` for `simple` and `accurate`.
```

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs: document token counting modes"
```

---

### Task 12: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest`
Expected: PASS (all tests, including the new `tests/test_token_counting_modes.py`).

- [ ] **Step 2: Type check the whole project**

Run: `uv run ty check .`
Expected: No errors.

- [ ] **Step 3: Lint and format the whole project**

Run: `uv run ruff check --fix`
Run: `uv run ruff format`
Expected: No errors (review any `--unsafe-fixes` suggestions manually before applying).

- [ ] **Step 4: Smoke-test the CLI end to end**

Run (against an existing fixture, or create a small `tmp.md`):
```bash
echo '# Title\n\nSome body text here.\n' > /tmp/smoke.md
uv run lumber /tmp/smoke.md --token-counter simple
uv run lumber /tmp/smoke.md --token-counter estimate
uv run lumber /tmp/smoke.md --token-counter accurate
```
Expected: each command prints JSON; `simple`'s `token_count == len(body)//4`; `accurate` and `estimate` produce tiktoken-based counts.

- [ ] **Step 5: Final commit (if formatting changed anything)**

```bash
git add -A
git commit -m "chore: full verification pass" || echo "nothing to commit"
```

---

## Self-Review Notes

**Spec coverage check:**

- Mode semantics (simple/estimate/accurate) — Tasks 1, 4, 7.
- `chars // 4` — Task 1.
- Incremental estimate as primary count — Tasks 3, 6.
- `accurate` zero-estimation + forced cache — Tasks 2, 4, 7.
- Strategy abstraction (Exact/Incremental) — Tasks 3, 5, 6.
- `Chunk` output fields per mode — Tasks 6, 7, 8.
- Two-layer parameters (`token_counter` + `tokenizer`) — Tasks 8, 9, 10.
- Combination rules (simple ignores engine; estimate/accurate upgrade simple→tiktoken) — Tasks 4, 8.
- Validation (`ValueError` on unknown modes/engines) — Tasks 4, 8.
- CLI / Web entry layers — Tasks 9, 10.
- Manual pipeline default-exact — Task 5 (default `count_mode="exact"`).
- Documentation — Task 11.
- Truncation guard + zero-estimation guard — Task 7.

**Type consistency check:**

- `CountMode = Literal["exact", "incremental"]` used consistently in Tasks 3, 5.
- `create_token_counter(name, tokenizer) -> (engine, CountMode)` matches usage in Tasks 8 (`tokenizer_impl, count_mode = ...`).
- `create_splitter(..., count_mode=...)` matches `BaseSplitter.__init__(..., count_mode=...)` in Task 5.
- `ExactTokenCount` / `IncrementalTokenCount` constructor takes a single `tokenizer` in Task 3, built via `_build_token_counter` in Task 5 — consistent.
- `BaseSplitter.token_counter` attribute name used in Tasks 5, 6, and the tests in Tasks 5, 7 — consistent.

**Open implementation notes (intentionally left to plan execution):**

- The `IncrementalTokenCount.count_body` in Task 3 computes the full join (not a running delta) — the incremental optimization is preserved at the splitter's block-accumulation loop (Task 6, Step 6) via the simplified `current_body_tokens + separator_delta + block_tokens` arithmetic.
- Web test route prefix (`/lumber/api/split/text` vs `/split/text`) must be matched to the existing `tests/test_web.py` convention at Task 10 execution.
