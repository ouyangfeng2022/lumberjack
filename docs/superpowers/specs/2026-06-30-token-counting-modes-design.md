# Token Counting Modes — Design

**Date:** 2026-06-30
**Status:** Design approved, pending implementation plan

## Motivation

The library currently offers two token counting pathways that are tangled
together:

1. A direct `tokenizer.count(body)` at chunk finalization
   (`core/splitters/base.py` → `_finalize_chunks`), whose accuracy depends on
   the tokenizer choice (`SimpleCharTokenizer` = per-character,
   `TiktokenTokenizer` = exact, but invoked with `cache=False` by default).
2. An incremental "additive estimate" that lives **inside the split process**
   (`_measure_section`, `_split_section_body`, `_separator_delta_after`,
   `_merge_drafts`). It accumulates `current - count(last) + count(last+sep) +
   block_tokens` deltas and uses an 8-character window to approximate the
   separator token delta. This estimate is surfaced as
   `Chunk.estimated_token_count` and is always computed regardless of
   tokenizer.

Both values are emitted on every `Chunk` today. The user wants three explicit,
mutually exclusive counting modes with clear cost/accuracy trade-offs, and wants
the existing additive estimate exposed as a first-class option rather than an
always-on side channel.

## Goals

- Expose three token counting modes: `simple`, `estimate`, `accurate`.
- `simple` mode uses the `chars // 4` heuristic (a common industry rule of
  thumb).
- `estimate` mode uses the existing additive incremental estimate as the
  **primary** count output, backed by a user-selectable tokenizer engine.
- `accurate` mode performs **no estimation at all**: every token count inside
  the splitter is computed in full against the rendered text, with caching
  forced on.
- Keep the tokenizer engine selectable for `estimate` / `accurate` modes.
- Preserve backward-compatible `Chunk` output fields.

## Non-Goals

- No new counting modes beyond the three.
- No rewrite of splitter control flow — only the counting call sites are routed
  through a strategy object.
- No parser-layer changes (parsers do not count tokens).
- No frontend (`lumberjack_webui/`) changes in this work.
- No refinement of the incremental delta algorithm (the 8-character window
  stays as-is).

## Mode Semantics

| Mode | Underlying engine | Splitter counting path | Final `token_count` |
|------|-------------------|------------------------|---------------------|
| `simple` | `chars // 4` (`ApproxCharTokenizer`) | **exact** | `len(body) // 4` (recomputed on full body) |
| `estimate` | user-selected tokenizer (defaults to `tiktoken`) | **incremental** (existing delta logic) | incremental estimate value |
| `accurate` | user-selected tokenizer (defaults to `tiktoken`), **cache forced on** | **exact** | `count(body, cache=True)` (recomputed on full body) |

### Why `simple` and `accurate` share the exact path

`chars // 4` is **not additive**: a 5-character text yields `1`, but splitting
it into `2 + 3` characters yields `0 + 0 = 0 ≠ 1`. Routing `simple` through the
incremental path would produce accumulate-vs-recompute mismatches. Routing it
through the exact path — applying `len(body) // 4` only to the final full text
— sidesteps the truncation problem entirely, and character counting is cheap
enough that full re-computation has no meaningful cost.

`accurate` shares the exact path by user requirement: "no estimation" means
every internal decision point counts the fully rendered text rather than
relying on additive deltas or window approximations.

### `Chunk` output fields per mode

| Mode | `token_count` | `estimated_token_count` |
|------|---------------|-------------------------|
| `simple` | `len(body) // 4` | same as `token_count` |
| `estimate` | incremental estimate | same as `token_count` |
| `accurate` | `count(body, cache=True)` | same as `token_count` (field retained for schema compatibility) |

The `estimated_token_count` field is retained in all modes for backward
schema compatibility; in `simple` and `accurate` it carries the same value as
`token_count`.

## Architecture

### Two counting paths inside the splitter

The splitter internally selects between two counting strategies based on the
mode:

- **exact** — every counting site fully concatenates the text and counts it.
  No additive deltas, no `_separator_delta_after` 8-character window. Used by
  `simple` and `accurate`.
- **incremental** — preserves the current additive / separator-delta logic.
  Used by `estimate` only.

### Counting strategy abstraction

A new internal strategy object encapsulates counting behavior so the splitter's
main logic stays mode-agnostic:

```
BaseSplitter
├── self.token_counter: TokenCountStrategy   # new
│     ├── ExactTokenCount       → count full text at every site
│     └── IncrementalTokenCount → reuse existing delta/window logic
```

The counting decision sites and their behavior per strategy:

| Decision site | Current implementation | exact | incremental |
|---------------|------------------------|-------|-------------|
| Measure section body (`_measure_section`) | per-block `count(text+sep)` accumulation | full `count(joined_body)` | current accumulation |
| Subtree separator delta | `_separator_delta_after` 8-char window | `count(tail+sep) - count(tail)` full | current window |
| Title tokens | `count("#"*level+" "+title+sep)` | unchanged (already full) | unchanged |
| `_split_section_body` running `current_body_tokens` | `-count(last)+count(last+sep)+block_tokens` | per-step `count(joined_so_far)` | current incremental |
| `_merge_drafts` merge delta | `_separator_delta_after(left_tail)` | full `count(merged_render)` | current delta |
| `_finalize_chunks` final `token_count` | `count(body)` | `count(body)` | skipped (use estimate) |

### Strategy interface (minimal set)

The strategy exposes the counting operations the splitter needs. Final method
shape is decided at plan time; the semantic surface is:

```python
class TokenCountStrategy(Protocol):
    def count_body(self, parts: list[str], separator: str) -> int: ...
    def count_text(self, text: str, *, cache: bool = False) -> int: ...
    def separator_delta(self, text: str, separator: str) -> int: ...
    def merge_delta(self, left_tail: str, ...) -> int: ...
```

- `ExactTokenCount` — every method counts the fully concatenated text. Simple,
  stateless, no additive tricks.
- `IncrementalTokenCount` — migrates the existing `_measure_section` /
  `_split_section_body` / `_separator_delta_after` arithmetic verbatim, just
  lifted out of splitter methods into the strategy object.

The splitter body changes only its call sites: e.g.
`self.tokenizer.count(block.text + SEPARATOR, cache=True)` becomes
`self.token_counter.count_body([block.text], SEPARATOR)`. Decision semantics
are unchanged; only the counting source is swapped.

## Two-Layer Parameters

The mode and the engine are orthogonal concerns, exposed as separate
parameters:

| Parameter | Role | Values | Default |
|-----------|------|--------|---------|
| `token_counter` (new) | counting strategy | `simple` / `estimate` / `accurate` | `simple` |
| `tokenizer` (retained) | underlying engine | `simple` / `tiktoken` | `simple` |

### Combination rules

- `token_counter=simple`: the `tokenizer` argument is **ignored**. Counting
  uses `chars // 4` directly via `ApproxCharTokenizer`; no heavy tokenizer is
  constructed or invoked.
- `token_counter=estimate`: uses the engine named by `tokenizer`. If
  `tokenizer` is unset or `simple`, it is upgraded to `tiktoken`. The
  incremental counting path is used.
- `token_counter=accurate`: uses the engine named by `tokenizer` (same default
  upgrade to `tiktoken`). The exact counting path is used, with caching forced
  on at every `count` call.

Validation: an unknown `token_counter` value raises `ValueError`; an unknown
`tokenizer` value raises `ValueError` (existing behavior preserved).

## Component Changes

### `core/tokenizers.py`

- **Keep** `SimpleCharTokenizer` (engine role).
- **Add** `ApproxCharTokenizer` implementing `TokenizerProtocol`:
  `count(text) -> len(text) // 4`. `encode` is a protocol placeholder (the
  splitter only uses `count`).
- **Extend** `TiktokenTokenizer` with a `default_cache: bool = False`
  constructor parameter. `count` / `encode` use `default_cache` when the caller
  does not pass `cache` explicitly. The `accurate` mode constructs an instance
  with `default_cache=True`.
- `create_tokenizer(name)` signature is unchanged; it still maps an engine name
  to a `TokenizerProtocol` instance.

### New: `create_token_counter(name, tokenizer)`

Introduces the mode concept. Returns a `(TokenizerProtocol, CountMode)` tuple
so the splitter can pick its counting strategy:

```python
def create_token_counter(
    name: str,                            # "simple" | "estimate" | "accurate"
    tokenizer: TokenizerProtocol | None = None,
) -> tuple[TokenizerProtocol, CountMode]:
    if name == "simple":
        return ApproxCharTokenizer(), "exact"
    engine = tokenizer or create_tokenizer("tiktoken")
    mode = "incremental" if name == "estimate" else "exact"
    # accurate forces cache on tiktoken engines
    ...
    return engine, mode
```

The precise mechanism for "forcing cache" in `accurate` mode is decided at
plan time; the spec only locks the semantics: in `accurate` mode, every
`count` call inside the splitter must run with `cache=True`.

Location: new function in `core/tokenizers.py` (or a dedicated helper module to
be decided at plan time).

### `lumber()`

New `token_counter` parameter; `tokenizer` retained:

```python
def lumber(
    ...,
    tokenizer: str = "simple",
    token_counter: str = "simple",
    ...,
):
```

Internally resolves the engine + mode via `create_token_counter` and forwards
both to the splitter factory.

### `create_splitter`

New `count_mode` parameter:

```python
splitter_impl = create_splitter(
    splitter,
    tokenizer=tokenizer_impl,
    count_mode=count_mode,
    options=options,
)
```

`BaseSplitter.__init__(tokenizer, options, count_mode="exact")` selects
`ExactTokenCount` or `IncrementalTokenCount`.

### CLI (`cli.py`)

- Keep `--tokenizer`.
- Add `--token-counter` with `choices=("simple", "estimate", "accurate")`,
  `default="simple"`.

### Web API (`web/routes.py`)

- `TextSplitRequest`: keep `tokenizer`, add `token_counter`.
- `split_file` form: keep `tokenizer` Form, add `token_counter` Form.
- `ChunkResponse` unchanged (`token_count` and `estimated_token_count`
  retained).

### Manual pipeline (custom tokenizer instance)

`RecursiveSplitter(tokenizer=my_tok)` still works. `BaseSplitter` gains an
optional `count_mode="exact"` parameter; the default `exact` is the safest
choice for users supplying their own tokenizer. Manual users wanting the
incremental path pass `count_mode="incremental"` explicitly.

## Testing

### A. `ApproxCharTokenizer` unit tests

- `count("hello world") == 11 // 4 == 2`
- Empty string → 0
- Unicode (CJK / emoji) counted by code point
- `encode` placeholder behavior (not exercised by the splitter)

### B. `create_token_counter` factory tests

- `simple` → `ApproxCharTokenizer` + `"exact"`
- `estimate` with no tokenizer → `tiktoken` + `"incremental"`
- `estimate` with `simple` tokenizer → upgraded to `tiktoken` + `"incremental"`
- `accurate` → `tiktoken` (with cache forced on) + `"exact"`
- Unknown `token_counter` → `ValueError`
- Unknown `tokenizer` → `ValueError`

### C. Strategy object tests

- `ExactTokenCount`: `count_body([a, b], sep) == tokenizer.count(a + sep + b)`
  (non-additive); `merge_delta` equals the full-recompute equivalent.
- `IncrementalTokenCount`: reproduces the existing `_separator_delta_after` /
  incremental arithmetic; matches `exact` on simple single-block cases (boundary
  divergences documented).

### D. Cross-mode boundary relationships

The three modes operate on **different token scales**, so universal boundary
equivalence does not hold. The test suite pins the two relationships that do:

1. **`estimate` vs `accurate` (same tiktoken engine):** both use the same
   engine, differing only in counting path (incremental vs exact). Boundaries
   match **except** where the incremental delta approximation flips a
   borderline decision. Tests assert that on typical inputs the chunk count and
   line ranges are identical, and document a constructed borderline case where
   they diverge (this is the same fixture used in section F).

2. **`simple` vs tiktoken modes:** different scales (`chars // 4` ≠ tiktoken
   tokens), so boundaries are expected to differ. Tests only assert that each
   mode internally produces well-formed chunks (every chunk's `token_count`
   within its budget semantics); no cross-scale boundary equality is claimed.

Existing `SimpleCharTokenizer` scenarios in `tests/test_splitter.py` are rerun
under the exact path to confirm the migration preserves current behavior.

### E. `simple` integer-truncation guard

Explicit test that `simple` mode's `token_count == len(body) // 4` — the core
reason `simple` cannot use the incremental path.

### F. `accurate` zero-estimation guard

Construct a scenario where incremental and full counts diverge (e.g. separator
boundary token merging) and assert that `accurate` mode's `token_count ==
count(body, cache=True)` (full truth), not the incremental value.

### G. Entry-layer tests

- CLI: `--token-counter` choices honored, default `simple`.
- Web: `token_counter` field accepts all three; `estimate` / `accurate` paths
  callable.
- `lumber()`: `token_counter=simple` ignores `tokenizer=tiktoken` (no heavy
  tokenizer constructed or invoked — test mechanism decided at plan time).
- Manual pipeline: `RecursiveSplitter(tokenizer=custom_tok)` defaults to
  `exact`; `count_mode="incremental"` switches paths.

### H. Existing test adjustments

- `test_splitter.py` / `test_api.py` scenarios that construct splitters with
  `SimpleCharTokenizer()` directly default to the exact path; behavior matches
  current logic (which already counts in full), so most assertions hold.
  `estimated_token_count` assertions (e.g. `tests/test_splitter.py:478`
  `== len("# A\n\nBody")`) must be re-verified per case.
- `test_api.py:219` (`lumber()` rejects tokenizer instances) is retained.

## Documentation

### `AGENTS.md`

- Commands section: CLI examples updated with `--token-counter`.
- Data Model / Splitting Rules: describe the three modes and the
  `token_count` / `estimated_token_count` values per mode.
- CLI Behavior: document `--token-counter` choices; redefine `--tokenizer` as
  the engine selector.

## Decision Record

- **Mode set**: `simple` / `estimate` / `accurate`, mutually exclusive
  single-select. (`estimate` retained as a first-class mode.)
- **`estimate` engine**: user-selected tokenizer, default `tiktoken`. Backed by
  the existing incremental delta logic.
- **`accurate` semantics**: zero estimation — full counts at every internal
  decision point, with caching forced on.
- **`simple` formula**: `chars // 4`.
- **Splitter path selection**: `simple` and `accurate` share the exact path;
  `estimate` uses the incremental path. Driven by integer-truncation
  non-additivity (`simple`) and the zero-estimation requirement (`accurate`).
- **Strategy abstraction**: `ExactTokenCount` / `IncrementalTokenCount` strategy
  objects inside `BaseSplitter`; splitter main logic stays mode-agnostic.
- **Parameter model**: `token_counter` (strategy) + `tokenizer` (engine),
  orthogonal. `simple` ignores the engine; `estimate` / `accurate` use it with
  a default upgrade to `tiktoken`.
- **`estimated_token_count` field**: retained in all modes for schema
  compatibility; equals `token_count` in `simple` and `accurate`.
- **Frontend**: out of scope for this work.
