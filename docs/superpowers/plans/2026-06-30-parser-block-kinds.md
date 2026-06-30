# Parser Block Kinds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add parser default block-kind surfaces and a MarkdownIt plugin block API that supports both declared token-kind mappings and custom block handlers.

**Architecture:** Keep parser-specific logic inside each parser package. DOCX and HTML expose fixed `default_block_kinds`; Markdown computes instance `block_kinds` from its defaults, active rules, `extra_block_kinds`, and `MarkdownBlockSpec` declarations. CLI block-config parsing receives explicit parser block kinds after input-format detection.

**Tech Stack:** Python 3.13, dataclasses, markdown-it-py tokens, pytest, ty, ruff, uv.

---

## File Structure

- Modify: `src/lumberjack/core/parsers/markdown/parser.py`
  - Add `MarkdownBlockSpec`, `MarkdownBlockContext`, and `MarkdownBlockHandler`.
  - Add `default_block_kinds`.
  - Remove `default_registry()`.
  - Add block-spec validation and handler dispatch.
  - Add public helper wrappers for handler code.
- Modify: `src/lumberjack/core/parsers/markdown/__init__.py`
  - Re-export `MarkdownBlockSpec`, `MarkdownBlockContext`, and `MarkdownBlockHandler`.
- Modify: `src/lumberjack/core/parsers/__init__.py`
  - Re-export the new Markdown block extension types.
- Modify: `src/lumberjack/core/parsers/docx/parser.py`
  - Rename `_BLOCK_KINDS` to `default_block_kinds`.
- Modify: `src/lumberjack/core/parsers/html/parser.py`
  - Rename `_BLOCK_KINDS` to `default_block_kinds`.
- Modify: `src/lumberjack/core/options.py`
  - Make `parse_cli_block_configs()` accept explicit `block_kinds`.
  - Remove the `MarkdownItParser.default_registry()` dependency.
- Modify: `src/lumberjack/cli.py`
  - Detect input format before parsing block configs.
  - Build the matching parser and validate CLI block configs against its `block_kinds`.
- Modify: `tests/test_parser.py`
  - Update default block-kind tests.
  - Add Markdown block-spec mapping, handler, fallback, and validation tests.
- Modify: `tests/test_docx_parser.py`
  - Add/extend default block-kind surface tests.
- Modify: `tests/test_html_parser.py`
  - Add default block-kind surface tests.
- Modify: `tests/test_api.py`
  - Update `parse_cli_block_configs()` calls to pass explicit block kinds.
  - Add a parser-specific block config test.
- Create: `tests/test_cli.py`
  - Add a CLI smoke test showing HTML `html_table` block config is accepted after format detection.

---

### Task 1: Parser Default Block-Kind Surfaces

**Files:**
- Modify: `tests/test_parser.py`
- Modify: `tests/test_docx_parser.py`
- Modify: `tests/test_html_parser.py`
- Modify: `src/lumberjack/core/parsers/markdown/parser.py`
- Modify: `src/lumberjack/core/parsers/docx/parser.py`
- Modify: `src/lumberjack/core/parsers/html/parser.py`

- [ ] **Step 1: Write failing tests for default block-kind surfaces**

In `tests/test_parser.py`, replace `test_default_block_kinds_match_parser()` with:

```python
def test_default_block_kinds_match_default_markdown_parser() -> None:
    """Markdown default_block_kinds must match a fresh default parser."""
    parser = MarkdownItParser()

    assert MarkdownItParser.default_block_kinds == parser.block_kinds
    assert "paragraph" in MarkdownItParser.default_block_kinds
    assert "code_fence" in MarkdownItParser.default_block_kinds
    assert "table" in MarkdownItParser.default_block_kinds
    assert "html_table" in MarkdownItParser.default_block_kinds
    assert not hasattr(MarkdownItParser, "default_registry")
```

In `tests/test_docx_parser.py`, update `test_docx_parser_block_kinds()` to:

```python
def test_docx_parser_block_kinds() -> None:
    parser = DocxParser()
    kinds = parser.block_kinds

    assert kinds == DocxParser.default_block_kinds
    assert "paragraph" in kinds
    assert "table" in kinds
    assert "list" in kinds
    assert isinstance(kinds, frozenset)
```

In `tests/test_html_parser.py`, add near the top after the first parser test:

```python
def test_html_parser_block_kinds_match_default_block_kinds() -> None:
    parser = HTMLParser()

    assert parser.block_kinds == HTMLParser.default_block_kinds
    assert "paragraph" in parser.block_kinds
    assert "html_table" in parser.block_kinds
    assert isinstance(parser.block_kinds, frozenset)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_parser.py::test_default_block_kinds_match_default_markdown_parser tests/test_docx_parser.py::test_docx_parser_block_kinds tests/test_html_parser.py::test_html_parser_block_kinds_match_default_block_kinds -q
```

Expected: FAIL because `default_block_kinds` is not defined and `MarkdownItParser.default_registry()` still exists.

- [ ] **Step 3: Implement default block-kind surfaces**

In `src/lumberjack/core/parsers/docx/parser.py`, replace `_BLOCK_KINDS` and the property body with:

```python
    default_block_kinds: ClassVar[frozenset[str]] = frozenset(
        {
            "paragraph",
            "table",
            "list",
            "list_item",
            "code_block",
            "blockquote",
            "front_matter",
        }
    )

    @property
    def block_kinds(self) -> frozenset[str]:
        """Block kinds this parser can produce."""
        return self.default_block_kinds
```

In the same file, change the typing import to:

```python
from typing import TYPE_CHECKING, Any, ClassVar
```

In `src/lumberjack/core/parsers/html/parser.py`, replace `_BLOCK_KINDS` and the property body with:

```python
    default_block_kinds: ClassVar[frozenset[str]] = frozenset(
        {
            "paragraph",
            "blockquote",
            "list",
            "list_item",
            "code_block",
            "html_block",
            "html_table",
            "front_matter",
        }
    )

    @property
    def block_kinds(self) -> frozenset[str]:
        """Block kinds this parser can produce."""
        return self.default_block_kinds
```

In `src/lumberjack/core/parsers/markdown/parser.py`:

Remove `BlockKindRegistry` from the model imports:

```python
from ...models import (
    DocumentAST,
    MarkdownBlock,
    MarkdownInline,
    SectionNode,
)
```

Inside `MarkdownItParser`, replace `_STRUCTURAL_KINDS`, `_default_registry`, and `default_registry()` with:

```python
    default_block_kinds: ClassVar[frozenset[str]] = frozenset(
        {
            "paragraph",
            "code_fence",
            "math_block",
            "math_block_eqno",
            "code_block",
            "html_block",
            "html_table",
            "blockquote",
            "list",
            "list_item",
            "table",
            "front_matter",
        }
    )
```

Then update `_compute_block_kinds()` to start from `default_block_kinds`:

```python
    def _compute_block_kinds(self) -> frozenset[str]:
        """Compute block kinds from parser defaults, active rules, and extensions."""
        active_rules = self._parser.get_active_rules().get("block", [])
        kinds: set[str] = set(self.default_block_kinds)
        for rule in active_rules:
            mapped = self._RULE_TO_KINDS.get(rule)
            if mapped is None:
                continue
            if isinstance(mapped, str):
                kinds.add(mapped)
            else:
                kinds.update(mapped)

        if "html_block" in kinds:
            kinds.add("html_table")

        return frozenset(kinds)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_parser.py::test_default_block_kinds_match_default_markdown_parser tests/test_docx_parser.py::test_docx_parser_block_kinds tests/test_html_parser.py::test_html_parser_block_kinds_match_default_block_kinds -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/test_parser.py tests/test_docx_parser.py tests/test_html_parser.py src/lumberjack/core/parsers/markdown/parser.py src/lumberjack/core/parsers/docx/parser.py src/lumberjack/core/parsers/html/parser.py
git commit -m "refactor(parser): expose default block kinds"
```

---

### Task 2: MarkdownBlockSpec Mapping and Validation

**Files:**
- Modify: `tests/test_parser.py`
- Modify: `src/lumberjack/core/parsers/markdown/parser.py`
- Modify: `src/lumberjack/core/parsers/markdown/__init__.py`
- Modify: `src/lumberjack/core/parsers/__init__.py`

- [ ] **Step 1: Write failing tests for spec mapping and validation**

In `tests/test_parser.py`, update imports:

```python
import pytest
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

from lumberjack.core.parsers.markdown.parser import (
    MarkdownBlockSpec,
    MarkdownItParser,
    MarkdownParser,
)
```

Add these tests near the existing unknown-token and plugin tests:

```python
def test_markdown_block_spec_maps_custom_token_to_declared_kind() -> None:
    parser = MarkdownItParser(
        block_specs=(
            MarkdownBlockSpec(
                kind="Callout",
                token_types=("callout_open",),
            ),
        )
    )
    parser._parser.parse = lambda _text, _env: [  # ty: ignore[invalid-assignment]
        Token("callout_open", "div", 1, map=[0, 1]),
        Token("callout_close", "div", -1),
    ]

    document = parser.parse("!!! note", document_title="callout.md")

    assert "callout" in parser.block_kinds
    assert document.root.blocks[0].kind == "callout"
    assert document.root.blocks[0].text == "!!! note"
    assert document.root.blocks[0].attrs["source_token_type"] == "callout_open"


def test_markdown_parser_extra_block_kinds_are_declared_without_token_mapping() -> None:
    parser = MarkdownItParser(extra_block_kinds=("Custom_Block", " aside "))

    assert "custom_block" in parser.block_kinds
    assert "aside" in parser.block_kinds


def test_markdown_block_spec_rejects_empty_kind() -> None:
    with pytest.raises(ValueError, match="block kind cannot be empty"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind=" ",
                    token_types=("callout_open",),
                ),
            )
        )


def test_markdown_block_spec_rejects_empty_token_type() -> None:
    with pytest.raises(ValueError, match="token type cannot be empty"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind="callout",
                    token_types=(" ",),
                ),
            )
        )


def test_markdown_block_spec_rejects_conflicting_token_kind_mapping() -> None:
    with pytest.raises(ValueError, match="conflicting block spec"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind="callout",
                    token_types=("custom_open",),
                ),
                MarkdownBlockSpec(
                    kind="aside",
                    token_types=("custom_open",),
                ),
            )
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_parser.py::test_markdown_block_spec_maps_custom_token_to_declared_kind tests/test_parser.py::test_markdown_parser_extra_block_kinds_are_declared_without_token_mapping tests/test_parser.py::test_markdown_block_spec_rejects_empty_kind tests/test_parser.py::test_markdown_block_spec_rejects_empty_token_type tests/test_parser.py::test_markdown_block_spec_rejects_conflicting_token_kind_mapping -q
```

Expected: FAIL because `MarkdownBlockSpec`, `block_specs`, and `extra_block_kinds` are not implemented.

- [ ] **Step 3: Add block spec dataclasses and constructor normalization**

In `src/lumberjack/core/parsers/markdown/parser.py`, replace the top import block with:

```python
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar
```

Keep the `TYPE_CHECKING` block focused on the MarkdownIt token import:

```python
if TYPE_CHECKING:
    from markdown_it.token import Token
```

Add these definitions above `InlineNormalizer`:

```python
@dataclass(slots=True, frozen=True)
class MarkdownBlockContext:
    """Context passed to custom Markdown block handlers."""

    parser: MarkdownItParser
    tokens: list[Token]
    index: int
    source_lines: list[str]
    token: Token


MarkdownBlockHandler = Callable[
    [MarkdownBlockContext],
    tuple[MarkdownBlock | None, int],
]


@dataclass(slots=True, frozen=True)
class MarkdownBlockSpec:
    """Declare how MarkdownIt token types map to lumberjack block kinds."""

    kind: str
    token_types: tuple[str, ...]
    handler: MarkdownBlockHandler | None = None
```

Update `MarkdownItParser.__init__()` signature:

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
```

At the start of `__init__()`, before parser setup, add:

```python
        (
            self._token_type_to_kind,
            self._block_handlers,
            self._extra_block_kinds,
        ) = self._normalize_block_extensions(block_specs, extra_block_kinds)
```

Add helper methods inside `MarkdownItParser`:

```python
    @staticmethod
    def _normalize_block_kind(kind: str) -> str:
        normalized = kind.strip().lower()
        if not normalized:
            raise ValueError("block kind cannot be empty")
        return normalized

    @staticmethod
    def _normalize_token_type(token_type: str) -> str:
        normalized = token_type.strip()
        if not normalized:
            raise ValueError("token type cannot be empty")
        return normalized

    def _normalize_block_extensions(
        self,
        block_specs: Iterable[MarkdownBlockSpec],
        extra_block_kinds: Iterable[str],
    ) -> tuple[dict[str, str], dict[str, MarkdownBlockHandler], frozenset[str]]:
        token_type_to_kind: dict[str, str] = {}
        handlers: dict[str, MarkdownBlockHandler] = {}

        for spec in block_specs:
            kind = self._normalize_block_kind(spec.kind)
            token_types = tuple(
                self._normalize_token_type(token_type)
                for token_type in spec.token_types
            )
            if not token_types:
                raise ValueError("block spec token_types cannot be empty")

            for token_type in token_types:
                existing_kind = token_type_to_kind.get(token_type)
                if existing_kind is not None and existing_kind != kind:
                    raise ValueError(
                        f"conflicting block spec for token type {token_type!r}: "
                        f"{existing_kind!r} != {kind!r}"
                    )

                if spec.handler is not None and token_type in handlers:
                    raise ValueError(
                        f"conflicting block spec handler for token type {token_type!r}"
                    )

                token_type_to_kind[token_type] = kind
                if spec.handler is not None:
                    handlers[token_type] = spec.handler

        normalized_extra_kinds = frozenset(
            self._normalize_block_kind(kind) for kind in extra_block_kinds
        )
        return token_type_to_kind, handlers, normalized_extra_kinds
```

Update `_compute_block_kinds()` to include extensions before returning:

```python
        kinds.update(self._extra_block_kinds)
        kinds.update(self._token_type_to_kind.values())
        return frozenset(kinds)
```

- [ ] **Step 4: Dispatch declared token types through generic block construction**

In `src/lumberjack/core/parsers/markdown/parser.py`, change `_build_fallback_block()` signature:

```python
    def _build_fallback_block(
        self,
        token: Token,
        tokens: list[Token],
        index: int,
        source_lines: list[str],
        *,
        kind: str | None = None,
    ) -> tuple[MarkdownBlock | None, int]:
```

Replace the derived kind line with:

```python
        block_kind = kind or token.type.removesuffix("_open")
```

Use `block_kind` in the `MarkdownBlock` constructor:

```python
                kind=block_kind,
```

In `_build_block()`, immediately before the final fallback return, add:

```python
        mapped_kind = self._token_type_to_kind.get(token.type)
        if mapped_kind is not None:
            return self._build_fallback_block(
                token,
                tokens,
                index,
                source_lines,
                kind=mapped_kind,
            )
```

- [ ] **Step 5: Re-export the new types**

In `src/lumberjack/core/parsers/markdown/__init__.py`, replace the file with:

```python
from .parser import (
    MarkdownBlockContext,
    MarkdownBlockHandler,
    MarkdownBlockSpec,
    MarkdownItParser,
    MarkdownParser,
)

__all__ = [
    "MarkdownBlockContext",
    "MarkdownBlockHandler",
    "MarkdownBlockSpec",
    "MarkdownItParser",
    "MarkdownParser",
]
```

In `src/lumberjack/core/parsers/__init__.py`, update the Markdown import:

```python
from .markdown import (
    MarkdownBlockContext,
    MarkdownBlockHandler,
    MarkdownBlockSpec,
    MarkdownItParser,
    MarkdownParser,
)
```

Update `__all__` in the same file to include:

```python
    "MarkdownBlockContext",
    "MarkdownBlockHandler",
    "MarkdownBlockSpec",
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_parser.py::test_markdown_block_spec_maps_custom_token_to_declared_kind tests/test_parser.py::test_markdown_parser_extra_block_kinds_are_declared_without_token_mapping tests/test_parser.py::test_markdown_block_spec_rejects_empty_kind tests/test_parser.py::test_markdown_block_spec_rejects_empty_token_type tests/test_parser.py::test_markdown_block_spec_rejects_conflicting_token_kind_mapping -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add tests/test_parser.py src/lumberjack/core/parsers/markdown/parser.py src/lumberjack/core/parsers/markdown/__init__.py src/lumberjack/core/parsers/__init__.py
git commit -m "feat(markdown): declare plugin block specs"
```

---

### Task 3: MarkdownBlockSpec Custom Handlers

**Files:**
- Modify: `tests/test_parser.py`
- Modify: `src/lumberjack/core/parsers/markdown/parser.py`

- [ ] **Step 1: Write failing tests for handler dispatch and helper wrappers**

In `tests/test_parser.py`, update the parser import to include context and model imports:

```python
from lumberjack.core.models import MarkdownBlock
from lumberjack.core.parsers.markdown.parser import (
    MarkdownBlockContext,
    MarkdownBlockSpec,
    MarkdownItParser,
    MarkdownParser,
)
```

Add these tests near the Task 2 block-spec tests:

```python
def test_markdown_block_spec_handler_builds_custom_block() -> None:
    seen_contexts: list[MarkdownBlockContext] = []

    def build_block(
        context: MarkdownBlockContext,
    ) -> tuple[MarkdownBlock | None, int]:
        seen_contexts.append(context)
        return (
            MarkdownBlock(
                kind="callout",
                text=f"handled:{context.token.content}",
                start_line=1,
                end_line=1,
                attrs={"source_token_type": context.token.type},
            ),
            context.index + 1,
        )

    parser = MarkdownItParser(
        block_specs=(
            MarkdownBlockSpec(
                kind="callout",
                token_types=("callout_block",),
                handler=build_block,
            ),
        )
    )
    parser._parser.parse = lambda _text, _env: [  # ty: ignore[invalid-assignment]
        Token("callout_block", "div", 0, map=[0, 1], content="note")
    ]

    document = parser.parse("!!! note", document_title="callout.md")

    assert seen_contexts
    assert seen_contexts[0].index == 0
    assert document.root.blocks[0].kind == "callout"
    assert document.root.blocks[0].text == "handled:note"
    assert document.root.blocks[0].attrs["source_token_type"] == "callout_block"


def test_markdown_block_spec_handler_can_parse_container_children() -> None:
    def build_container(
        context: MarkdownBlockContext,
    ) -> tuple[MarkdownBlock | None, int]:
        close_index = context.parser.find_matching_close(
            context.tokens,
            context.index,
        )
        children = context.parser.parse_child_blocks(
            context.tokens,
            context.index + 1,
            close_index,
            context.source_lines,
        )
        return (
            MarkdownBlock(
                kind="callout",
                text="\n\n".join(child.text for child in children),
                start_line=1,
                end_line=2,
                children=children,
                attrs={"source_token_type": context.token.type},
            ),
            close_index + 1,
        )

    inline = Token("inline", "", 0, map=[1, 2], content="Body")
    inline.children = [Token("text", "", 0, content="Body")]
    parser = MarkdownItParser(
        block_specs=(
            MarkdownBlockSpec(
                kind="callout",
                token_types=("callout_open",),
                handler=build_container,
            ),
        )
    )
    parser._parser.parse = lambda _text, _env: [  # ty: ignore[invalid-assignment]
        Token("callout_open", "div", 1, map=[0, 2]),
        Token("paragraph_open", "p", 1, map=[1, 2]),
        inline,
        Token("paragraph_close", "p", -1),
        Token("callout_close", "div", -1),
    ]

    document = parser.parse("!!! note\nBody", document_title="callout.md")

    block = document.root.blocks[0]
    assert block.kind == "callout"
    assert block.text == "Body"
    assert block.children[0].kind == "paragraph"
    assert block.children[0].text == "Body"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_parser.py::test_markdown_block_spec_handler_builds_custom_block tests/test_parser.py::test_markdown_block_spec_handler_can_parse_container_children -q
```

Expected: FAIL because handlers are stored but not dispatched, and public helper wrappers do not exist.

- [ ] **Step 3: Add handler dispatch and helper wrappers**

In `src/lumberjack/core/parsers/markdown/parser.py`, add these public helper wrappers inside `MarkdownItParser` near `_parse_blocks()` and `_find_matching_close()`:

```python
    def parse_child_blocks(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        source_lines: list[str],
    ) -> tuple[MarkdownBlock, ...]:
        """Parse child block tokens for custom block handlers."""
        return self._parse_blocks(tokens, start, end, source_lines)

    def find_matching_close(self, tokens: list[Token], index: int) -> int:
        """Return the matching close-token index for custom block handlers."""
        return self._find_matching_close(tokens, index)
```

In `_build_block()`, immediately before the mapped-kind branch from Task 2, add:

```python
        handler = self._block_handlers.get(token.type)
        if handler is not None:
            return handler(
                MarkdownBlockContext(
                    parser=self,
                    tokens=tokens,
                    index=index,
                    source_lines=source_lines,
                    token=token,
                )
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_parser.py::test_markdown_block_spec_handler_builds_custom_block tests/test_parser.py::test_markdown_block_spec_handler_can_parse_container_children -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/test_parser.py src/lumberjack/core/parsers/markdown/parser.py
git commit -m "feat(markdown): support custom block handlers"
```

---

### Task 4: CLI Block Configs Use Parser Block Kinds

**Files:**
- Modify: `tests/test_api.py`
- Create: `tests/test_cli.py`
- Modify: `src/lumberjack/core/options.py`
- Modify: `src/lumberjack/cli.py`

- [ ] **Step 1: Write failing tests for explicit CLI block kinds**

In `tests/test_api.py`, add this import:

```python
from lumberjack.core.parsers.html import HTMLParser
```

Update `test_parse_cli_block_configs_json_overrides_short_config()` to pass explicit Markdown block kinds:

```python
def test_parse_cli_block_configs_json_overrides_short_config() -> None:
    block_options = parse_cli_block_configs(
        ["table:isolated:500"],
        block_kinds=MarkdownItParser().block_kinds,
        json_config='{"table": {"repeat_header": false}}',
    )

    table = block_options["table"]
    assert table.isolated is False
    assert table.max_tokens is None
    assert table == TableBlockParams(repeat_header=False)
```

Add this test near it:

```python
def test_parse_cli_block_configs_uses_supplied_parser_block_kinds() -> None:
    block_options = parse_cli_block_configs(
        ["html_table:isolated"],
        block_kinds=HTMLParser().block_kinds,
    )

    html_table = block_options["html_table"]
    assert isinstance(html_table, TableBlockParams)
    assert html_table.isolated is True
```

Create `tests/test_cli.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

from lumberjack.cli import main


def test_cli_validates_block_configs_against_detected_html_format(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        "<h1>Guide</h1><table><tr><th>A</th></tr><tr><td>1</td></tr></table>",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lumber",
            str(html_path),
            "--max-tokens",
            "500",
            "--block-config",
            "html_table:isolated",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["document"] == "Guide"
    assert payload["chunk_count"] >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_api.py::test_parse_cli_block_configs_json_overrides_short_config tests/test_api.py::test_parse_cli_block_configs_uses_supplied_parser_block_kinds tests/test_cli.py::test_cli_validates_block_configs_against_detected_html_format -q
```

Expected: FAIL because `parse_cli_block_configs()` does not accept `block_kinds`, and CLI still validates against Markdown defaults before format detection.

- [ ] **Step 3: Update options parsing**

In `src/lumberjack/core/options.py`, remove this import:

```python
from .parsers.markdown.parser import MarkdownItParser
```

Replace `parse_cli_block_configs()` with:

```python
def parse_cli_block_configs(
    entries: list[str],
    *,
    block_kinds: frozenset[str],
    json_config: str = "",
) -> dict[str, BaseParams]:
    """Parse CLI ``--block-config`` entries against explicit parser block kinds."""
    registry = BlockKindRegistry(block_kinds)
    result: dict[str, BaseParams] = dict(registry.default_handling())
    for entry in entries:
        kind, params = parse_block_config_entry(entry, registry)
        result[kind] = params
    if json_config and json_config.strip():
        json_overrides = parse_block_config_json(json_config)
        if json_overrides:
            result.update(json_overrides)
    return result
```

- [ ] **Step 4: Update CLI format detection before block config parsing**

In `src/lumberjack/cli.py`, add imports:

```python
from .core.parsers import create_parser
from .formats import detect_format
```

Replace the `block_options` assignment in `main()` with:

```python
    input_format = detect_format(input_path, args.input_format)
    parser_impl = create_parser(input_format)
    block_options = parse_cli_block_configs(
        args.block_config,
        block_kinds=parser_impl.block_kinds,
        json_config=args.block_config_json,
    )
```

Pass the resolved format into `lumber()`:

```python
        format=input_format,
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_api.py::test_parse_cli_block_configs_json_overrides_short_config tests/test_api.py::test_parse_cli_block_configs_uses_supplied_parser_block_kinds tests/test_cli.py::test_cli_validates_block_configs_against_detected_html_format -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add tests/test_api.py tests/test_cli.py src/lumberjack/core/options.py src/lumberjack/cli.py
git commit -m "fix(cli): validate block configs by input parser"
```

---

### Task 5: Custom Kind Block Options and Regression Coverage

**Files:**
- Modify: `tests/test_api.py`
- Modify: `tests/test_parser.py`

- [ ] **Step 1: Write failing or regression tests for custom kind block options and fallback preservation**

In `tests/test_api.py`, add this test near other block option tests:

```python
def test_resolve_block_options_accepts_markdown_block_spec_kind() -> None:
    parser = MarkdownItParser(
        block_specs=(
            MarkdownBlockSpec(
                kind="callout",
                token_types=("callout_open",),
            ),
        )
    )

    options = resolve_block_options(
        parser.block_kinds,
        {"callout": {"isolated": True, "max_tokens": 25}},
    )

    assert options["callout"].isolated is True
    assert options["callout"].max_tokens == 25
```

Update the imports in `tests/test_api.py` to include:

```python
from lumberjack.core.parsers.markdown.parser import MarkdownBlockSpec, MarkdownItParser
```

In `tests/test_parser.py`, keep the existing fallback test and add an assertion to it:

```python
    assert "mystery_block" not in parser.block_kinds
```

This proves unknown runtime fallback still works without declaring every possible token kind in advance.

- [ ] **Step 2: Run tests to verify behavior**

Run:

```bash
uv run pytest tests/test_api.py::test_resolve_block_options_accepts_markdown_block_spec_kind tests/test_parser.py::test_markdown_it_parser_preserves_unknown_block_tokens_as_raw_markdown -q
```

Expected before Task 2 implementation: FAIL for missing `MarkdownBlockSpec`. Expected after Task 2 implementation: PASS.

- [ ] **Step 3: Verify the test import uses the parser module**

The implementation import line in `tests/test_api.py` must be:

```python
from lumberjack.core.parsers.markdown.parser import MarkdownBlockSpec, MarkdownItParser
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_api.py::test_resolve_block_options_accepts_markdown_block_spec_kind tests/test_parser.py::test_markdown_it_parser_preserves_unknown_block_tokens_as_raw_markdown -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/test_api.py tests/test_parser.py
git commit -m "test(parser): cover custom block options"
```

---

### Task 6: Full Verification and Cleanup

**Files:**
- Review: `src/lumberjack/core/parsers/markdown/parser.py`
- Review: `src/lumberjack/core/options.py`
- Review: `src/lumberjack/cli.py`
- Review: `tests/test_parser.py`
- Review: `tests/test_api.py`
- Review: `tests/test_cli.py`

- [ ] **Step 1: Search for removed registry API**

Run:

```bash
rg -n "default_registry|_default_registry|MarkdownItParser.default_registry|parse_cli_block_configs\\(" src tests README.md README.zh-CN.md
```

Expected: no `default_registry` matches. `parse_cli_block_configs(` matches should all pass `block_kinds=`.

- [ ] **Step 2: Run type check**

Run:

```bash
uv run ty check .
```

Expected: PASS.

- [ ] **Step 3: Run ruff check with fixes**

Run:

```bash
uv run ruff check --fix
```

Expected: PASS or auto-fixed import ordering only.

- [ ] **Step 4: Run ruff format**

Run:

```bash
uv run ruff format
```

Expected: PASS.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_parser.py tests/test_api.py tests/test_docx_parser.py tests/test_html_parser.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 7: Commit cleanup when formatting changed files**

Run:

```bash
git status --short
```

When `ruff` changed files after the previous task commits, commit only those formatting or cleanup changes:

```bash
git add src tests
git commit -m "chore: format parser block kind changes"
```

Expected: either a clean working tree or one cleanup commit.

---

## Self-Review

- Spec coverage:
  - Parser `default_block_kinds`: Task 1.
  - Markdown `extra_block_kinds`: Task 2.
  - Markdown token-kind mapping: Task 2.
  - Markdown custom handlers and context: Task 3.
  - Unknown token fallback preserved: Task 5.
  - `resolve_block_options(parser.block_kinds, ...)`: Task 5.
  - CLI validation against resolved parser format: Task 4.
  - Remove `MarkdownItParser.default_registry()` dependency: Tasks 1, 4, 6.
- Placeholder scan:
  - No placeholder markers or open-ended implementation instructions remain.
  - Each code-changing task includes concrete tests, implementation snippets, commands, and expected outcomes.
- Type consistency:
  - The public types are `MarkdownBlockSpec`, `MarkdownBlockContext`, and `MarkdownBlockHandler`.
  - The parser constructor arguments are `block_specs` and `extra_block_kinds`.
  - The helper wrappers are `find_matching_close()` and `parse_child_blocks()`.
  - `parse_cli_block_configs()` requires keyword-only `block_kinds`.
