from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.front_matter import front_matter_plugin

from lumberjack.block import BlockKind

from ..._internal.rendering import join_rendered_blocks
from .plugins import brackets_math_plugin

if TYPE_CHECKING:
    from markdown_it.token import Token

from ...models import DocumentAST, DocumentBlock, DocumentInline, SectionNode
from ...protocols import ParserProtocol

LINK_REFERENCE_DEFINITION_RE = re.compile(r"^[ ]{0,3}\[([^\]]+)\]:")


def slice_source(source_lines: list[str], line_map: Any) -> str:
    """Extract source text for a half-open [start, end) line range."""
    if not isinstance(line_map, (list, tuple)) or len(line_map) != 2:
        return ""
    start, end = int(line_map[0]), int(line_map[1])
    if start < 0 or end < start:
        return ""
    return "\n".join(source_lines[start:end]).strip("\n")


def start_line(token: Token) -> int | None:
    if token.map is None:
        return None
    return int(token.map[0]) + 1


def end_line(token: Token) -> int | None:
    if token.map is None:
        return None
    return int(token.map[1])


def is_tight_list(tokens: list[Token], start: int, end: int) -> bool:
    return any(
        token.type == "paragraph_open" and token.hidden
        for token in tokens[start : end + 1]
    )


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
    tuple[DocumentBlock | None, int],
]


@dataclass(slots=True, frozen=True)
class MarkdownBlockSpec:
    """Declare how MarkdownIt token types map to lumberjack block kinds."""

    kind: str
    token_types: tuple[str, ...]
    handler: MarkdownBlockHandler | None = None


class InlineNormalizer:
    """Converts markdown-it inline tokens into lumberjack DocumentInline nodes and renders them back."""

    def token_to_inlines(self, token: Token | None) -> tuple[DocumentInline, ...]:
        if token is None:
            return ()
        return self.normalize_tokens(token.children or [])

    def normalize_tokens(self, tokens: list[Token]) -> tuple[DocumentInline, ...]:
        result, _ = self.collect_tokens(tokens, 0)
        return result

    def collect_tokens(
        self,
        tokens: list[Token],
        index: int,
        *,
        stop_types: set[str] | None = None,
    ) -> tuple[tuple[DocumentInline, ...], int]:
        normalized: list[DocumentInline] = []
        while index < len(tokens):
            token = tokens[index]
            if stop_types is not None and token.type in stop_types:
                break

            if token.type.endswith("_close"):
                index += 1
                continue

            if token.type == "text":
                normalized.append(DocumentInline(kind="text", text=token.content))
                index += 1
                continue

            if token.type == "code_inline":
                normalized.append(
                    DocumentInline(
                        kind="code_span",
                        text=token.content,
                        attrs={"literal": token.content},
                    )
                )
                index += 1
                continue

            if token.type == "math_inline":
                normalized.append(
                    DocumentInline(
                        kind="math_inline",
                        text=token.content,
                        attrs={"literal": token.content},
                    )
                )
                index += 1
                continue

            if token.type == "html_inline":
                normalized.append(
                    DocumentInline(kind="inline_html", text=token.content)
                )
                index += 1
                continue

            if token.type in {"softbreak", "hardbreak"}:
                normalized.append(
                    DocumentInline(
                        kind="soft_break"
                        if token.type == "softbreak"
                        else "hard_break",
                        text="\n",
                    )
                )
                index += 1
                continue

            if token.type == "image":
                normalized.append(
                    DocumentInline(
                        kind="image",
                        children=self.normalize_tokens(token.children or []),
                        attrs={
                            "destination": str((token.attrs or {}).get("src") or ""),
                            "title": str((token.attrs or {}).get("title") or ""),
                        },
                    )
                )
                index += 1
                continue

            if token.type == "footnote_ref":
                normalized.append(
                    DocumentInline(
                        kind="footnote_ref",
                        text=f"[^{token.meta.get('label', '')}]",
                        attrs={
                            "source_token_type": token.type,
                            "meta": dict(token.meta)
                            if isinstance(token.meta, dict)
                            else token.meta,
                        },
                    )
                )
                index += 1
                continue

            if token.type == "footnote_anchor":
                normalized.append(
                    DocumentInline(
                        kind="footnote_anchor",
                        text="",
                        attrs={
                            "source_token_type": token.type,
                            "meta": dict(token.meta)
                            if isinstance(token.meta, dict)
                            else token.meta,
                        },
                    )
                )
                index += 1
                continue

            if token.type in {"em_open", "strong_open", "s_open", "link_open"}:
                kind_map = {
                    "em_open": "emphasis",
                    "strong_open": "strong",
                    "s_open": "strikethrough",
                    "link_open": "autolink"
                    if token.markup in {"autolink", "linkify"}
                    else "link",
                }
                close_type_map = {
                    "em_open": "em_close",
                    "strong_open": "strong_close",
                    "s_open": "s_close",
                    "link_open": "link_close",
                }
                children, index = self.collect_tokens(
                    tokens,
                    index + 1,
                    stop_types={close_type_map[token.type]},
                )
                if index < len(tokens):
                    index += 1

                attrs = {
                    "destination": str((token.attrs or {}).get("href") or ""),
                    "title": str((token.attrs or {}).get("title") or ""),
                }
                if token.type == "link_open" and token.markup in {
                    "autolink",
                    "linkify",
                }:
                    attrs["literal"] = self.render_inlines(children)
                    attrs["syntax"] = str(token.markup or "link")
                normalized.append(
                    DocumentInline(
                        kind=kind_map[token.type],
                        children=children,
                        attrs=attrs,
                    )
                )
                continue

            if token.type.endswith("_open"):
                close_type = f"{token.type.removesuffix('_open')}_close"
                children, index = self.collect_tokens(
                    tokens,
                    index + 1,
                    stop_types={close_type},
                )
                if index < len(tokens):
                    index += 1
                normalized.append(
                    DocumentInline(
                        kind=token.type.removesuffix("_open"),
                        children=children,
                        attrs={
                            "source_token_type": token.type,
                            "markup": str(token.markup or ""),
                            "meta": dict(token.meta)
                            if isinstance(token.meta, dict)
                            else token.meta,
                        },
                    )
                )
                continue

            if token.children:
                normalized.extend(self.normalize_tokens(token.children))
                index += 1
                continue

            normalized.append(DocumentInline(kind=token.type, text=token.content))
            index += 1

        return (tuple(normalized), index)

    def render_inlines(self, inlines: Iterable[DocumentInline]) -> str:
        return "".join(self.render_inline(inline) for inline in inlines)

    def render_inline(self, node: DocumentInline) -> str:
        if node.kind == "text":
            return node.text
        if node.kind == "code_span":
            return f"`{node.attrs.get('literal', node.text)}`"
        if node.kind == "math_inline":
            return f"${node.attrs.get('literal', node.text)}$"
        if node.kind == "emphasis":
            return f"*{self.render_inlines(node.children)}*"
        if node.kind == "strong":
            return f"**{self.render_inlines(node.children)}**"
        if node.kind == "strikethrough":
            return f"~~{self.render_inlines(node.children)}~~"
        if node.kind == "link":
            title = str(node.attrs.get("title") or "").strip()
            title_suffix = f' "{title}"' if title else ""
            return (
                f"[{self.render_inlines(node.children)}]"
                f"({node.attrs.get('destination', '')}{title_suffix})"
            )
        if node.kind == "image":
            title = str(node.attrs.get("title") or "").strip()
            title_suffix = f' "{title}"' if title else ""
            return (
                f"![{self.render_inlines(node.children)}]"
                f"({node.attrs.get('destination', '')}{title_suffix})"
            )
        if node.kind == "autolink":
            literal = str(
                node.attrs.get("literal") or self.render_inlines(node.children)
            )
            if node.attrs.get("syntax") == "autolink":
                return f"<{literal}>"
            return literal or str(node.attrs.get("destination", ""))
        if node.kind == "inline_html":
            return node.text
        if node.kind in {"soft_break", "hard_break"}:
            return "\n"
        if node.children:
            return self.render_inlines(node.children)
        return node.text


class MarkdownItParser(ParserProtocol[str]):
    """Parse Markdown with markdown-it-py and normalize tokens into lumberjack's document model."""

    # Token-type → DocumentBlock.kind mapping for simple (non-container) blocks.
    # Used by _build_block to look up block kinds from token types.
    _BLOCK_KIND_MAP: ClassVar[dict[str, str]] = {
        "paragraph_open": "paragraph",
        "fence": "code_fence",
        "math_block": "math_block",
        "math_block_eqno": "math_block_eqno",
        "code_block": "code_block",
        "html_block": "html_block",
    }

    # Block rule name → block kind(s) produced by that rule.
    # Used by _compute_block_kinds() to translate active rules into block kinds.
    # Rules not listed here (hr, reference, heading, lheading) produce no block kinds.
    _RULE_TO_KINDS: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "paragraph": "paragraph",
        "fence": "code_fence",
        "code": "code_block",
        "html_block": "html_block",
        "blockquote": "blockquote",
        "list": ("list", "list_item"),
        "table": "table",
        "front_matter": "front_matter",
        "math_block": "math_block",
        "math_block_eqno": "math_block_eqno",
    }

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
    _BUILTIN_BLOCK_TOKEN_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "front_matter",
            "heading_open",
            "paragraph_open",
            "blockquote_open",
            "bullet_list_open",
            "ordered_list_open",
            "list_item_open",
            "fence",
            "math_block",
            "math_block_eqno",
            "code_block",
            "html_block",
            "hr",
            "table_open",
        }
    )

    @staticmethod
    def _normalize_block_kind(kind: str) -> str:
        if not isinstance(kind, str):
            raise TypeError("block kind must be a string")
        normalized = kind.strip().lower()
        if not normalized:
            raise ValueError("block kind cannot be empty")
        return normalized

    @staticmethod
    def _normalize_token_type(token_type: str) -> str:
        if not isinstance(token_type, str):
            raise TypeError("token type must be a string")
        normalized = token_type.strip()
        if not normalized:
            raise ValueError("token type cannot be empty")
        return normalized

    def _normalize_block_extensions(
        self,
        block_specs: Iterable[MarkdownBlockSpec],
    ) -> tuple[dict[str, str], dict[str, MarkdownBlockHandler]]:
        token_type_to_kind: dict[str, str] = {}
        handlers: dict[str, MarkdownBlockHandler] = {}

        for spec in block_specs:
            kind = self._normalize_block_kind(spec.kind)
            if isinstance(spec.token_types, str | bytes):
                raise TypeError("token_types must be an iterable of strings")
            token_types = tuple(
                self._normalize_token_type(token_type)
                for token_type in spec.token_types
            )
            if not token_types:
                raise ValueError("block spec token_types cannot be empty")
            if spec.handler is not None and not callable(spec.handler):
                raise TypeError("block spec handler must be callable")

            for token_type in token_types:
                if token_type in self._BUILTIN_BLOCK_TOKEN_TYPES:
                    raise ValueError(
                        f"block spec token type {token_type!r} is handled internally"
                    )

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

        return token_type_to_kind, handlers

    def _compute_block_kinds(self) -> frozenset[str]:
        """Compute block kinds from this parser's active rules and extensions."""
        active_rules = self._parser.get_active_rules().get("block", [])
        kinds: set[str] = set()
        for rule in active_rules:
            mapped = self._RULE_TO_KINDS.get(rule)
            if mapped is None:
                continue
            if isinstance(mapped, str):
                kinds.add(mapped)
            else:
                kinds.update(mapped)

        # Add html_table as a dynamically detected block kind
        # HTML tables are detected within html_block content during parsing
        if "html_block" in kinds:
            kinds.add("html_table")

        kinds.update(self._token_type_to_kind.values())
        return frozenset(kinds)

    @property
    def block_kinds(self) -> frozenset[str]:
        """Block kinds this parser instance can produce, based on active rules."""
        return self._block_kinds

    def __init__(
        self,
        preset: str = "gfm-like",
        *,
        plugins: Iterable[Callable[..., None]] = (),
        block_specs: Iterable[MarkdownBlockSpec] = (),
        options_update: dict[str, Any] | None = None,
        disable_lheading: bool = True,
    ) -> None:
        (
            self._token_type_to_kind,
            self._block_handlers,
        ) = self._normalize_block_extensions(block_specs)
        self._inline = InlineNormalizer()
        self._parser = MarkdownIt(preset, options_update=options_update)
        self._parser.use(dollarmath_plugin)
        self._parser.use(front_matter_plugin)
        self._parser.use(brackets_math_plugin)
        for plugin in plugins:
            self._parser.use(plugin)
        if disable_lheading:
            self._parser.disable("lheading")
        self._block_kinds = self._compute_block_kinds()

    def parse(
        self,
        data: str,
        *,
        document_title: str | None = None,
        metadata_overrides: Mapping[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocumentAST:
        """Parse raw Markdown text into a ``DocumentAST`` with section tree and reference definitions.

        Args:
            data: Raw Markdown text to parse.
            document_title: Optional override for the document title.
            metadata_overrides: Semantic metadata that overrides values parsed
                from front matter.
            source_path: Optional source provenance stored separately from metadata.

        Raises:
            TypeError: If ``data`` is not a ``str``.
        """
        if not isinstance(data, str):
            msg = f"MarkdownParser.parse expects str, got {type(data).__name__}"
            raise TypeError(msg)

        metadata = dict(metadata_overrides or {})

        env: dict[str, Any] = {}
        tokens = self._parser.parse(data, env)
        source_lines = data.splitlines()

        root = SectionNode(level=0, title="")
        section_stack: list[SectionNode] = [root]
        index = 0

        while index < len(tokens):
            token = tokens[index]
            if token.type == "front_matter":
                section_stack[-1].add_block(
                    DocumentBlock(
                        kind=BlockKind.FRONT_MATTER,
                        text=slice_source(source_lines, token.map),
                        start_line=start_line(token),
                        end_line=end_line(token),
                    )
                )
                index += 1
                continue
            if token.type == "heading_open":
                section, index = self._build_section(tokens, index, section_stack)
                section_stack[-1].add_child(section)
                section_stack.append(section)
                continue

            block, index = self._build_block(tokens, index, source_lines)
            if block is not None:
                section_stack[-1].add_block(block)

        fm_metadata = self._parse_front_matter(tokens)
        if fm_metadata is not None:
            for key, value in fm_metadata.items():
                metadata.setdefault(key, value)

        final_title = self._resolve_document_title(document_title, fm_metadata, root)
        root.title = final_title

        return DocumentAST(
            title=final_title,
            source=data,
            root=root,
            source_path=str(source_path) if source_path is not None else None,
            metadata=metadata,
            reference_definitions=self._extract_reference_definitions(
                env, source_lines
            ),
        )

    def _build_section(
        self,
        tokens: list[Token],
        index: int,
        section_stack: list[SectionNode],
    ) -> tuple[SectionNode, int]:
        """Build a ``SectionNode`` from a heading_open token, adjusting the stack for hierarchy."""
        token = tokens[index]
        close_index = self._find_matching_close(tokens, index)
        inline_token = tokens[index + 1] if index + 1 < len(tokens) else None
        title_inlines = self._inline.token_to_inlines(inline_token)
        title = self._inline.render_inlines(title_inlines).strip()
        level = int(token.tag[1:]) if token.tag.startswith("h") else 1
        section_start = start_line(token)

        while section_stack and section_stack[-1].level >= level:
            section_stack.pop()
        parent = section_stack[-1]
        return (
            SectionNode(
                level=level,
                title=title,
                path=(*parent.path, (level, title)),
                index=len(parent.children),
                start_line=section_start,
                title_inlines=title_inlines,
            ),
            close_index + 1,
        )

    def _build_block(
        self,
        tokens: list[Token],
        index: int,
        source_lines: list[str],
        *,
        allow_headings: bool = False,
    ) -> tuple[DocumentBlock | None, int]:
        """Normalize the token at *index* into a ``DocumentBlock``, returning the next token index."""
        token = tokens[index]

        if token.type == "heading_open":
            close_index = self._find_matching_close(tokens, index)
            if not allow_headings:
                inline_token = tokens[index + 1] if index + 1 < len(tokens) else None
                inlines = self._inline.token_to_inlines(inline_token)
                return (
                    DocumentBlock(
                        kind=BlockKind.PARAGRAPH,
                        text=slice_source(source_lines, token.map),
                        start_line=start_line(token),
                        end_line=end_line(token),
                        inlines=inlines,
                    ),
                    close_index + 1,
                )
            return (None, close_index + 1)

        if token.type == "paragraph_open":
            close_index = self._find_matching_close(tokens, index)
            inline_token = tokens[index + 1] if index + 1 < len(tokens) else None
            inlines = self._inline.token_to_inlines(inline_token)
            return (
                DocumentBlock(
                    kind=BlockKind.PARAGRAPH,
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    inlines=inlines,
                ),
                close_index + 1,
            )

        if token.type == "blockquote_open":
            close_index = self._find_matching_close(tokens, index)
            children = self._parse_blocks(tokens, index + 1, close_index, source_lines)
            return (
                DocumentBlock(
                    kind=BlockKind.BLOCKQUOTE,
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    children=children,
                ),
                close_index + 1,
            )

        if token.type in {"bullet_list_open", "ordered_list_open"}:
            close_index = self._find_matching_close(tokens, index)
            children = self._parse_blocks(tokens, index + 1, close_index, source_lines)
            attrs = {
                "ordered": token.type == "ordered_list_open",
                "start": int((token.attrs or {}).get("start") or 1),
                "tight": is_tight_list(tokens, index, close_index),
                "bullet": f"{token.markup or '-'}",
            }
            return (
                DocumentBlock(
                    kind=BlockKind.LIST,
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    children=children,
                    attrs=attrs,
                ),
                close_index + 1,
            )

        if token.type == "list_item_open":
            close_index = self._find_matching_close(tokens, index)
            children = self._parse_blocks(tokens, index + 1, close_index, source_lines)
            return (
                DocumentBlock(
                    kind=BlockKind.LIST_ITEM,
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    children=children,
                ),
                close_index + 1,
            )

        if token.type == "fence":
            info = token.info.strip()
            language = info.split(maxsplit=1)[0] if info else ""
            return (
                DocumentBlock(
                    kind=BlockKind.CODE_FENCE,
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    attrs={
                        "language": language,
                        "info": info,
                        "literal": token.content.rstrip("\n"),
                    },
                ),
                index + 1,
            )

        if token.type == "math_block":
            return (
                DocumentBlock(
                    kind=BlockKind.MATH_BLOCK,
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    attrs={"literal": token.content.rstrip("\n")},
                ),
                index + 1,
            )

        if token.type == "math_block_eqno":
            return (
                DocumentBlock(
                    kind=BlockKind.MATH_BLOCK_EQNO,
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    attrs={
                        "literal": token.content.rstrip("\n"),
                        "eqno": token.info.strip(),
                    },
                ),
                index + 1,
            )

        if token.type == "code_block":
            return (
                DocumentBlock(
                    kind=BlockKind.CODE_BLOCK,
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    attrs={"literal": token.content.rstrip("\n")},
                ),
                index + 1,
            )

        if token.type == "html_block":
            # Check if the HTML block contains a table
            from ..html.table_parser import HTMLTableParser

            html_content = slice_source(source_lines, token.map)
            html_parser = HTMLTableParser()

            if html_parser.contains_table(html_content):
                # Treat HTML tables as html_table blocks for independent handling
                return (
                    DocumentBlock(
                        kind=BlockKind.HTML_TABLE,
                        text=html_content,
                        start_line=start_line(token),
                        end_line=end_line(token),
                        attrs={
                            "literal": token.content.rstrip("\n"),
                        },
                    ),
                    index + 1,
                )

            return (
                DocumentBlock(
                    kind=BlockKind.HTML_BLOCK,
                    text=html_content,
                    start_line=start_line(token),
                    end_line=end_line(token),
                    attrs={"literal": token.content.rstrip("\n")},
                ),
                index + 1,
            )

        if token.type == "hr":
            return (None, index + 1)

        if token.type == "table_open":
            close_index = self._find_matching_close(tokens, index)
            return (
                DocumentBlock(
                    kind=BlockKind.TABLE,
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                ),
                close_index + 1,
            )

        mapped_kind = self._token_type_to_kind.get(token.type)
        if mapped_kind is not None:
            handler = self._block_handlers.get(token.type)
            if handler is None:
                return self._build_fallback_block(
                    token,
                    tokens,
                    index,
                    source_lines,
                    kind=mapped_kind,
                )

            block, next_index = handler(
                MarkdownBlockContext(
                    parser=self,
                    tokens=tokens,
                    index=index,
                    source_lines=source_lines,
                    token=token,
                )
            )
            if block is not None and block.kind != mapped_kind:
                raise ValueError(
                    "Markdown block handler returned undeclared block kind "
                    f"{block.kind!r} for token type {token.type!r}; "
                    f"expected {mapped_kind!r}"
                )
            return block, next_index

        raise ValueError(
            "undeclared Markdown block token "
            f"{token.type!r}; add a MarkdownBlockSpec for custom plugin tokens"
        )

    def _parse_blocks(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        source_lines: list[str],
    ) -> tuple[DocumentBlock, ...]:
        """Parse tokens in the half-open range [start, end) into a tuple of blocks."""
        blocks: list[DocumentBlock] = []
        index = start
        while index < end:
            block, index = self._build_block(
                tokens, index, source_lines, allow_headings=False
            )
            if block is not None and block.text:
                blocks.append(block)
        return tuple(blocks)

    def parse_child_blocks(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        source_lines: list[str],
    ) -> tuple[DocumentBlock, ...]:
        """Parse child block tokens for custom block handlers."""
        return self._parse_blocks(tokens, start, end, source_lines)

    def find_matching_close(self, tokens: list[Token], index: int) -> int:
        """Return the matching close-token index for custom block handlers."""
        return self._find_matching_close(tokens, index)

    def _find_matching_close(self, tokens: list[Token], index: int) -> int:
        """Return the index of the matching *_close token for an *_open token at *index*."""
        token = tokens[index]
        if not token.type.endswith("_open"):
            return index

        close_type = f"{token.type[:-5]}_close"
        depth = 0
        for current in range(index, len(tokens)):
            current_token = tokens[current]
            if current_token.type == token.type:
                depth += 1
            elif current_token.type == close_type:
                depth -= 1
                if depth == 0:
                    return current
        raise ValueError(f"Unbalanced token stream: missing {close_type}")

    def _build_fallback_block(
        self,
        token: Token,
        tokens: list[Token],
        index: int,
        source_lines: list[str],
        *,
        kind: str,
    ) -> tuple[DocumentBlock | None, int]:
        """Handle unrecognized token types by capturing source text and children."""
        if token.type.endswith("_close") or token.type == "inline":
            return (None, index + 1)

        close_index = (
            self._find_matching_close(tokens, index)
            if token.type.endswith("_open")
            else index
        )
        children = (
            self._parse_blocks(tokens, index + 1, close_index, source_lines)
            if token.type.endswith("_open")
            else ()
        )
        text = slice_source(source_lines, token.map)
        if not text and children:
            text = join_rendered_blocks(
                [child.text for child in children if child.text]
            )
        if not text.strip():
            return (None, close_index + 1)

        return (
            DocumentBlock(
                kind=kind,
                text=text,
                start_line=start_line(token),
                end_line=end_line(token),
                children=children,
                attrs={
                    "source_token_type": token.type,
                    "markup": str(token.markup or ""),
                    "meta": dict(token.meta)
                    if isinstance(token.meta, dict)
                    else token.meta,
                },
            ),
            close_index + 1,
        )

    def _parse_front_matter(
        self,
        tokens: list[Token],
    ) -> dict[str, object] | None:
        """Parse YAML front matter from the first token, if it is a ``front_matter`` token."""
        if not tokens or tokens[0].type != "front_matter":
            return None
        try:
            parsed = yaml.safe_load(tokens[0].content)
        except yaml.YAMLError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    def _resolve_document_title(
        self,
        document_title: str | None,
        fm_metadata: dict[str, object] | None,
        root: SectionNode,
    ) -> str:
        """Resolve document title by priority: user-provided > front_matter > first H1 > Anonymous."""
        if document_title is not None:
            return document_title
        if fm_metadata is not None:
            title = fm_metadata.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()
        h1_title = self._first_h1_title(root)
        if h1_title is not None:
            return h1_title
        return "Anonymous"

    @staticmethod
    def _first_h1_title(root: SectionNode) -> str | None:
        """Return the title of the first level-1 heading section, or None."""
        for child in root.children:
            if child.level == 1:
                return child.title
        return None

    def _extract_reference_definitions(
        self,
        env: dict[str, Any],
        source_lines: list[str],
    ) -> dict[str, dict[str, str]]:
        """Extract link reference definitions from the markdown-it parse environment."""
        references = env.get("references")
        if not isinstance(references, dict):
            return {}

        definitions: dict[str, dict[str, str]] = {}
        for normalized_label, payload in references.items():
            if not isinstance(payload, dict):
                continue
            label = self._recover_reference_label(
                payload.get("map"),
                source_lines,
                fallback=str(normalized_label),
            )
            definitions[label] = {
                "destination": str(payload.get("href") or ""),
                "title": str(payload.get("title") or ""),
            }
        return definitions

    def _recover_reference_label(
        self,
        line_map: Any,
        source_lines: list[str],
        *,
        fallback: str,
    ) -> str:
        """Recover the original bracket label for a link reference definition."""
        if isinstance(line_map, list) and len(line_map) == 2:
            excerpt = slice_source(source_lines, line_map)
            for line in excerpt.splitlines():
                match = LINK_REFERENCE_DEFINITION_RE.match(line)
                if match:
                    return match.group(1)
        return fallback


MarkdownParser = MarkdownItParser
