# Parser Block Kinds and Markdown Plugin Blocks

**Date:** 2026-06-30
**Status:** Approved (design phase)
**Scope:** parser block-kind declarations, MarkdownIt custom block handling,
and CLI block-config resolution.

## Problem

`MarkdownItParser` accepts custom MarkdownIt plugins through its `plugins`
argument, but it does not expose a first-class way to describe or handle new
block tokens produced by those plugins.

Today, block-kind behavior is split across a few places:

- `MarkdownItParser._RULE_TO_KINDS` maps MarkdownIt block rule names to
  lumberjack `MarkdownBlock.kind` values for `block_kinds` discovery.
- `_build_block()` has bespoke handling for built-in token types.
- Unknown block tokens fall through to `_build_fallback_block()`, which derives
  a kind from `token.type.removesuffix("_open")`.
- `MarkdownItParser.default_registry()` creates a registry from a default
  Markdown parser instance, and the CLI uses that default Markdown registry
  before it knows the actual input format.
- `DocxParser` and `HTMLParser` expose fixed `_BLOCK_KINDS`, while Markdown
  computes its kinds dynamically.

This leaves two practical gaps:

1. A plugin can produce a new block kind, but callers cannot declare the kind
   and its handling in a standard public API.
2. Each parser should have a simple default set of block kinds, then merge in
   parser-instance extensions to form the final `parser.block_kinds`.

## Goals

- Give every parser a clear default block-kind surface:
  `default_block_kinds`.
- Make each parser instance expose final block kinds as its
  `default_block_kinds` plus any parser-specific extras. Built-in DOCX and HTML
  have no extras today; Markdown can add kinds discovered from active rules and
  user declarations.
- Add a Markdown-specific extension API that lets users declare new plugin
  block kinds and optionally provide custom block construction logic.
- Preserve the current fallback behavior for unknown MarkdownIt tokens.
- Simplify block-config resolution so callers can use `parser.block_kinds`
  directly instead of reaching for `default_registry()`.
- Let the CLI validate `--block-config` against the resolved parser format,
  including HTML and DOCX.

## Non-Goals

- No new generic plugin system for DOCX or HTML parsing.
- No changes to the `DocumentAST`, `SectionNode`, `MarkdownBlock`, or
  `MarkdownInline` dataclass fields.
- No LangChain dependency or splitter-specific plugin layer.
- No compatibility shim for older internal names. The project is in
  development and `AGENTS.md` allows disruptive changes.
- No changes to built-in MarkdownIt plugin behavior beyond normalizing the
  exposed block-kind API.

## Design

### Parser Default Block Kinds

Each parser exposes a class-level `default_block_kinds`:

```python
class DocxParser:
    default_block_kinds = frozenset({...})

class HTMLParser:
    default_block_kinds = frozenset({...})

class MarkdownItParser:
    default_block_kinds = frozenset({...})
```

For DOCX and HTML, there are no parser-specific extras today, so the instance
property remains simple:

```python
@property
def block_kinds(self) -> frozenset[str]:
    return self.default_block_kinds
```

For Markdown, `block_kinds` is instance-specific because active MarkdownIt
rules and user extensions can vary:

```python
@property
def block_kinds(self) -> frozenset[str]:
    return self._block_kinds
```

`MarkdownItParser._block_kinds` is computed from:

- `default_block_kinds`
- active MarkdownIt rules translated through the built-in rule-to-kind map
- `html_table` when `html_block` is possible
- user-declared `extra_block_kinds`
- user-declared `BlockSpec.kind` values

### Markdown BlockSpec

Add a public dataclass near `MarkdownItParser`:

```python
@dataclass(slots=True, frozen=True)
class MarkdownBlockSpec:
    kind: str
    token_types: tuple[str, ...]
    handler: MarkdownBlockHandler | None = None
```

`kind` is the normalized lumberjack block kind. `token_types` are MarkdownIt
token types that should map to that kind. `handler` is optional. A simple plugin
can use only `kind` and `token_types`; a complex plugin can provide a handler.

The handler type is:

```python
MarkdownBlockHandler = Callable[
    [MarkdownBlockContext],
    tuple[MarkdownBlock | None, int],
]
```

`MarkdownBlockContext` is a small frozen dataclass containing the data a custom
handler needs without exposing parser internals as positional arguments:

```python
@dataclass(slots=True, frozen=True)
class MarkdownBlockContext:
    parser: MarkdownItParser
    tokens: list[Token]
    index: int
    source_lines: list[str]
    token: Token
```

The handler returns the same shape as `_build_block()`: a block (or `None`) and
the next token index. Returning the next index keeps container tokens and
multi-token constructs possible without adding another abstraction.

### MarkdownItParser Constructor

Extend the constructor with two optional keyword-only arguments:

```python
def __init__(
    self,
    preset: str = "gfm-like",
    *,
    plugins: Iterable[Callable[..., None]] = (),
    block_specs: Iterable[MarkdownBlockSpec] = (),
    extra_block_kinds: Iterable[str] = (),
    options_update: dict[str, Any] | None = None,
    disable_lheading: bool = False,
    max_heading_level: int | None = None,
) -> None:
    ...
```

Constructor behavior:

- Apply built-in MarkdownIt plugins first, then user `plugins`, as today.
- Normalize `block_specs` into:
  - `self._block_specs_by_token_type`
  - `self._token_type_to_kind`
- Normalize `extra_block_kinds` to lowercase stripped names.
- Compute final `self._block_kinds` after MarkdownIt rules are configured and
  after `disable_lheading` is applied.

Duplicate `token_types` are allowed only when they map to the same kind and
only one spec provides a handler. Conflicting mappings raise `ValueError`
during parser construction. Empty kind names and empty token type names also
raise `ValueError`.

### Markdown Token Handling Order

`_build_block()` uses this order:

1. Built-in specialized handlers for known token types:
   `heading_open`, `paragraph_open`, `blockquote_open`, list tokens, code
   blocks, math blocks, `html_block`, `table_open`, and `hr`.
2. A user `MarkdownBlockSpec.handler` for `token.type`, if one is registered.
3. A user `token_type -> kind` mapping from `MarkdownBlockSpec`, using generic
   block construction.
4. Existing fallback behavior for unrecognized tokens, deriving the kind from
   `token.type.removesuffix("_open")`.

Built-in handlers win over user specs. This keeps core Markdown behavior stable
and prevents accidental replacement of paragraph/list/table semantics. If
custom replacement is needed later, it can be designed explicitly.

### Generic Block Construction

For a spec with no handler, the parser uses the existing fallback mechanics but
with the spec's normalized `kind` instead of deriving the kind from the token
type.

For leaf tokens, it captures source text from `token.map`, line numbers, and
attrs including `source_token_type`, `markup`, and `meta`.

For container open tokens, it finds the matching close token, recursively parses
child blocks, joins child text when source text is empty, and advances past the
close token.

This keeps the lightweight API useful while preserving the richer fallback
behavior that already exists.

### BlockKindRegistry and Defaults

Keep `BlockKindRegistry` as the validation/default-handling helper, but make
callers build it from an explicit parser:

```python
registry = BlockKindRegistry(parser.block_kinds)
```

Remove `MarkdownItParser.default_registry()` and update callers/tests to build
registries from an explicit parser instance. The project is in development, so
there is no compatibility shim.

`resolve_block_options(parser.block_kinds, overrides)` remains the main API for
manual pipelines and `lumber()`.

### CLI Block Config Resolution

The CLI should resolve the input format before parsing `--block-config`:

1. Build `input_path`.
2. Resolve the effective format using `detect_format(input_path,
   args.input_format)`.
3. Create the matching built-in parser with `create_parser(effective_format)`.
4. Parse CLI block config entries against `parser.block_kinds`.
5. Pass the already parsed `block_options` into `lumber()`.

This lets CLI users configure `html_table` for HTML input and DOCX-specific
defaults without going through the Markdown default registry.

To avoid parsing/constructing a separate parser twice becoming a concern, this
can be revisited later. For now the built-in parser construction cost is tiny,
and `lumber()` already owns the actual parse.

## Examples

Lightweight plugin declaration:

```python
parser = MarkdownItParser(
    plugins=(admonition_plugin,),
    block_specs=(
        MarkdownBlockSpec(
            kind="admonition",
            token_types=("admonition_open",),
        ),
    ),
)
```

Custom handler declaration:

```python
def build_admonition(
    context: MarkdownBlockContext,
) -> tuple[MarkdownBlock | None, int]:
    token = context.token
    close_index = context.parser.find_matching_close(context.tokens, context.index)
    children = context.parser.parse_child_blocks(
        context.tokens,
        context.index + 1,
        close_index,
        context.source_lines,
    )
    return (
        MarkdownBlock(
            kind="admonition",
            text="\n\n".join(child.text for child in children),
            start_line=start_line(token),
            end_line=end_line(token),
            children=children,
            attrs={"source_token_type": token.type, "meta": dict(token.meta)},
        ),
        close_index + 1,
    )
```

The exact helper names exposed for handlers should be small and intentional.
If exposing private methods directly feels too leaky during implementation, add
public wrappers such as `find_matching_close()` and `parse_child_blocks()` that
delegate to the existing private methods.

## Testing

Add focused tests before implementation:

1. `DocxParser.default_block_kinds` and `HTMLParser.default_block_kinds` match
   their `block_kinds` properties.
2. `MarkdownItParser.default_block_kinds` contains the built-in default kinds
   and a default instance exposes those kinds through `block_kinds`.
3. A `MarkdownBlockSpec` without a handler adds its kind to
   `parser.block_kinds` and maps a custom token type to that kind.
4. A `MarkdownBlockSpec` handler is called and can return a custom
   `MarkdownBlock`.
5. Unknown MarkdownIt tokens without a spec still use the existing fallback
   kind derived from token type.
6. Conflicting `MarkdownBlockSpec` token mappings raise `ValueError`.
7. `resolve_block_options(parser.block_kinds, ...)` accepts a custom spec kind.
8. CLI block-config parsing can validate against HTML `html_table` kinds after
   format detection.

Verification after implementation:

```bash
uv run ty check .
uv run ruff check --fix
uv run ruff format
uv run pytest tests/test_parser.py tests/test_api.py tests/test_docx_parser.py tests/test_html_parser.py
```

Run broader `uv run pytest` if the focused tests pass and runtime stays
reasonable.

## Risks

- **Handler surface too leaky:** Passing the parser into
  `MarkdownBlockContext` is powerful but exposes internal methods if handlers
  call private APIs. Prefer small public helper wrappers for common needs.
- **Token/rule confusion:** MarkdownIt rule names and token types are different
  concepts. `BlockSpec` should use token types because handlers consume token
  streams. `_RULE_TO_KINDS` remains internal for active-rule discovery.
- **Built-in override expectations:** Users might expect custom specs to
  replace built-in handlers. This design intentionally avoids that for now.
  Replacement semantics can be added later with an explicit flag if needed.
- **CLI double parser construction:** The CLI will create a parser for
  block-config validation and `lumber()` will create another parser to parse
  the document. This is acceptable for the current built-in parsers.
