from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.front_matter import front_matter_plugin

from ..core.plugins import brackets_math_plugin
from ..utils import join_markdown

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from typing import ClassVar

    from markdown_it.token import Token

    from ..base.interfaces import MarkdownParserProtocol
    from ..models import DocumentAST, MarkdownBlock, MarkdownInline, SectionNode

from ..models import (
    BlockKindRegistry,
    DocumentAST,
    MarkdownBlock,
    MarkdownInline,
    SectionNode,
)

LINK_REFERENCE_DEFINITION_RE = re.compile(r"^[ ]{0,3}\[([^\]]+)\]:")


def slice_source(source_lines: list[str], line_map: Any) -> str:
    """Extract source text for a half-open [start, end) line range."""
    if not isinstance(line_map, (list, tuple)) or len(line_map) != 2:
        return ""
    start, end = int(line_map[0]), int(line_map[1])
    if start < 0 or end < start:
        return ""
    return "\n".join(source_lines[start:end])


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


class InlineNormalizer:
    """Converts markdown-it inline tokens into lumberjack MarkdownInline nodes and renders them back."""

    def token_to_inlines(self, token: Token | None) -> tuple[MarkdownInline, ...]:
        if token is None:
            return ()
        return self.normalize_tokens(token.children or [])

    def normalize_tokens(self, tokens: list[Token]) -> tuple[MarkdownInline, ...]:
        result, _ = self.collect_tokens(tokens, 0)
        return result

    def collect_tokens(
        self,
        tokens: list[Token],
        index: int,
        *,
        stop_types: set[str] | None = None,
    ) -> tuple[tuple[MarkdownInline, ...], int]:
        normalized: list[MarkdownInline] = []
        while index < len(tokens):
            token = tokens[index]
            if stop_types is not None and token.type in stop_types:
                break

            if token.type.endswith("_close"):
                index += 1
                continue

            if token.type == "text":
                normalized.append(MarkdownInline(kind="text", text=token.content))
                index += 1
                continue

            if token.type == "code_inline":
                normalized.append(
                    MarkdownInline(
                        kind="code_span",
                        text=token.content,
                        attrs={"literal": token.content},
                    )
                )
                index += 1
                continue

            if token.type == "math_inline":
                normalized.append(
                    MarkdownInline(
                        kind="math_inline",
                        text=token.content,
                        attrs={"literal": token.content},
                    )
                )
                index += 1
                continue

            if token.type == "html_inline":
                normalized.append(
                    MarkdownInline(kind="inline_html", text=token.content)
                )
                index += 1
                continue

            if token.type in {"softbreak", "hardbreak"}:
                normalized.append(
                    MarkdownInline(
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
                    MarkdownInline(
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
                    MarkdownInline(
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
                    MarkdownInline(
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
                    MarkdownInline(
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
                    MarkdownInline(
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

            normalized.append(MarkdownInline(kind=token.type, text=token.content))
            index += 1

        return (tuple(normalized), index)

    def render_inlines(self, inlines: Iterable[MarkdownInline]) -> str:
        return "".join(self.render_inline(inline) for inline in inlines)

    def render_inline(self, node: MarkdownInline) -> str:
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


class MarkdownItParser:
    """Parse Markdown with markdown-it-py and normalize tokens into lumberjack's document model."""

    # Token-type → MarkdownBlock.kind mapping for simple (non-container) blocks.
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

    # Block kinds that are always present regardless of active rules,
    # produced by structural handling in _build_block.
    _STRUCTURAL_KINDS: ClassVar[frozenset[str]] = frozenset(
        {
            "paragraph",  # heading_open fallback when allow_headings=False
            "list_item",  # list_item_open inside list containers
        }
    )

    def _compute_block_kinds(self) -> frozenset[str]:
        """Compute block kinds from the parser's active block rules."""
        active_rules = self._parser.get_active_rules().get("block", [])
        kinds: set[str] = set(self._STRUCTURAL_KINDS)
        for rule in active_rules:
            mapped = self._RULE_TO_KINDS.get(rule)
            if mapped is None:
                continue
            if isinstance(mapped, str):
                kinds.add(mapped)
            else:
                kinds.update(mapped)
        return frozenset(kinds)

    @property
    def block_kinds(self) -> frozenset[str]:
        """Block kinds this parser instance can produce, based on active rules."""
        return self._block_kinds

    _default_registry: BlockKindRegistry | None = None

    @classmethod
    def default_registry(cls) -> BlockKindRegistry:
        """Lazy-loaded registry built from the default parser configuration.

        This is the single source of truth for default block kinds — used by
        CLI, web routes, and ``SplitOptions`` when no explicit ``block_kinds``
        are provided.
        """
        if cls._default_registry is None:
            cls._default_registry = BlockKindRegistry(cls().block_kinds)
        return cls._default_registry

    def __init__(
        self,
        preset: str = "gfm-like",
        *,
        plugins: Iterable[Callable[..., None]] = (),
        options_update: dict[str, Any] | None = None,
        disable_lheading: bool = False,
    ) -> None:
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
        text: str,
        *,
        document_title: str | None = None,
        document_metadata: dict[str, object] | None = None,
    ) -> DocumentAST:
        """Parse raw Markdown text into a ``DocumentAST`` with section tree and reference definitions."""
        if document_metadata is None:
            document_metadata = {}

        env: dict[str, Any] = {}
        tokens = self._parser.parse(text, env)
        source_lines = text.splitlines()

        root = SectionNode(level=0, title="")
        section_stack: list[SectionNode] = [root]
        index = 0

        while index < len(tokens):
            token = tokens[index]
            if token.type == "front_matter":
                section_stack[-1].add_block(
                    MarkdownBlock(
                        kind="front_matter",
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
                document_metadata.setdefault(key, value)

        final_title = self._resolve_document_title(document_title, fm_metadata, root)
        root.title = final_title

        return DocumentAST(
            title=final_title,
            source=text,
            root=root,
            metadata=document_metadata,
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
    ) -> tuple[MarkdownBlock | None, int]:
        """Normalize the token at *index* into a ``MarkdownBlock``, returning the next token index."""
        token = tokens[index]

        if token.type == "heading_open":
            close_index = self._find_matching_close(tokens, index)
            if not allow_headings:
                inline_token = tokens[index + 1] if index + 1 < len(tokens) else None
                inlines = self._inline.token_to_inlines(inline_token)
                return (
                    MarkdownBlock(
                        kind="paragraph",
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
                MarkdownBlock(
                    kind="paragraph",
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
                MarkdownBlock(
                    kind="blockquote",
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
                MarkdownBlock(
                    kind="list",
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
                MarkdownBlock(
                    kind="list_item",
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
                MarkdownBlock(
                    kind="code_fence",
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
                MarkdownBlock(
                    kind="math_block",
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    attrs={"literal": token.content.rstrip("\n")},
                ),
                index + 1,
            )

        if token.type == "math_block_eqno":
            return (
                MarkdownBlock(
                    kind="math_block_eqno",
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
                MarkdownBlock(
                    kind="code_block",
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                    attrs={"literal": token.content.rstrip("\n")},
                ),
                index + 1,
            )

        if token.type == "html_block":
            return (
                MarkdownBlock(
                    kind="html_block",
                    text=slice_source(source_lines, token.map),
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
                MarkdownBlock(
                    kind="table",
                    text=slice_source(source_lines, token.map),
                    start_line=start_line(token),
                    end_line=end_line(token),
                ),
                close_index + 1,
            )

        return self._build_fallback_block(token, tokens, index, source_lines)

    def _parse_blocks(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        source_lines: list[str],
    ) -> tuple[MarkdownBlock, ...]:
        """Parse tokens in the half-open range [start, end) into a tuple of blocks."""
        blocks: list[MarkdownBlock] = []
        index = start
        while index < end:
            block, index = self._build_block(
                tokens, index, source_lines, allow_headings=False
            )
            if block is not None and block.text:
                blocks.append(block)
        return tuple(blocks)

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
    ) -> tuple[MarkdownBlock | None, int]:
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
            text = join_markdown([child.text for child in children if child.text])
        if not text.strip():
            return (None, close_index + 1)

        kind = token.type.removesuffix("_open")

        return (
            MarkdownBlock(
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


def create_parser(
    name: str, *, disable_lheading: bool = False
) -> MarkdownParserProtocol:
    """Instantiate a parser by name (``"default"`` or ``"markdown-it"``)."""
    normalized = name.strip().lower()
    if normalized in {"default", "markdown-it"}:
        return MarkdownItParser(disable_lheading=disable_lheading)
    raise ValueError(f"Unsupported parser: {name}")
