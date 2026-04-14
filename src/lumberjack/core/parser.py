from __future__ import annotations

import re
from typing import Any

from ..base.interfaces import MarkdownParserProtocol
from ..models import DocumentAST, MarkdownBlock, MarkdownInline, SectionNode

ATX_HEADING_RE = re.compile(r"^[ ]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
OPEN_FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$")
THEMATIC_BREAK_RE = re.compile(r"^[ ]{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})[ \t]*$")


class _SourceLocator:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.cursor = 0

    def find_heading(self, level: int, title: str) -> int | None:
        for index in range(self.cursor, len(self.lines)):
            match = ATX_HEADING_RE.match(self.lines[index])
            if match and len(match.group(1)) == level and match.group(2).strip() == title:
                self.cursor = index + 1
                return index + 1
        return None

    def find_block(
        self,
        *,
        kind: str,
        block_text: str,
        literal: str = "",
    ) -> tuple[int | None, int | None]:
        if not block_text.strip():
            return (None, None)

        specialized_matchers = {
            "code_block": lambda: self._find_indented_code_block(literal),
            "code_fence": lambda: self._find_fenced_code_block(literal),
            "thematic_break": self._find_thematic_break,
        }
        specialized_matcher = specialized_matchers.get(kind)
        if specialized_matcher is not None:
            matched = specialized_matcher()
            if matched is not None:
                return matched

        target_lines = block_text.splitlines()
        for index in range(self.cursor, len(self.lines)):
            matched = self._match_block_at(index, target_lines)
            if matched is not None:
                start, end = matched
                self.cursor = end
                return (start + 1, end)
        return (None, None)

    def _match_block_at(self, start_index: int, target_lines: list[str]) -> tuple[int, int] | None:
        source_index = start_index
        target_index = 0

        while source_index < len(self.lines) and target_index < len(target_lines):
            if self.lines[source_index].rstrip() != target_lines[target_index].rstrip():
                return None
            source_index += 1
            target_index += 1

        if target_index != len(target_lines):
            return None
        return (start_index, source_index)

    def _find_thematic_break(self) -> tuple[int, int] | None:
        for index in range(self.cursor, len(self.lines)):
            if THEMATIC_BREAK_RE.match(self.lines[index]):
                self.cursor = index + 1
                return (index + 1, index + 1)
        return None

    def _find_fenced_code_block(self, literal: str) -> tuple[int, int] | None:
        body_lines = literal.splitlines()
        for index in range(self.cursor, len(self.lines)):
            opening_match = OPEN_FENCE_RE.match(self.lines[index])
            if opening_match is None:
                continue

            closing_pattern = re.compile(
                rf"^[ ]{{0,3}}{re.escape(opening_match.group(1)[0])}"
                rf"{{{len(opening_match.group(1))},}}[ \t]*$"
            )
            source_index = index + 1
            target_index = 0

            while source_index < len(self.lines) and target_index < len(body_lines):
                if self.lines[source_index].rstrip() != body_lines[target_index].rstrip():
                    break
                source_index += 1
                target_index += 1

            if target_index != len(body_lines):
                continue
            if source_index >= len(self.lines) or not closing_pattern.match(
                self.lines[source_index]
            ):
                continue

            self.cursor = source_index + 1
            return (index + 1, source_index + 1)
        return None

    def _find_indented_code_block(self, literal: str) -> tuple[int, int] | None:
        literal_lines = literal.splitlines()
        if not literal_lines:
            return None

        for index in range(self.cursor, len(self.lines)):
            if not self._looks_like_indented_code_line(self.lines[index]):
                continue

            source_index = index
            target_index = 0
            while source_index < len(self.lines) and target_index < len(literal_lines):
                if (
                    self._deindent_code_line(self.lines[source_index])
                    != literal_lines[target_index]
                ):
                    break
                source_index += 1
                target_index += 1

            if target_index != len(literal_lines):
                continue

            self.cursor = source_index
            return (index + 1, source_index)
        return None

    def _looks_like_indented_code_line(self, line: str) -> bool:
        return line.startswith("    ") or line.startswith("\t")

    def _deindent_code_line(self, line: str) -> str:
        if line.startswith("\t"):
            return line[1:]
        if line.startswith("    "):
            return line[4:]
        if not line.strip():
            return ""
        return line


class CommonMarkASTParser(MarkdownParserProtocol):
    """Normalize a CommonMark AST into lumberjack's internal document model."""

    def parse(
        self,
        text: str,
        *,
        document_title: str = "document.md",
        document_metadata: dict[str, object] | None = None,
    ) -> DocumentAST:
        ast = self._parse_to_ast(text)
        root = SectionNode(level=0, title=document_title)
        section_stack: list[SectionNode] = [root]
        locator = _SourceLocator(text)

        for child in ast.get("children", []):
            if not isinstance(child, dict) or child.get("element") == "blank_line":
                continue

            if child.get("element") == "heading":
                section = self._build_section(child, locator, section_stack)
                section_stack[-1].add_child(section)
                section_stack.append(section)
                continue

            block = self._build_block(child, locator=locator)
            if block is not None:
                section_stack[-1].add_block(block)

        return DocumentAST(
            title=document_title,
            source=text,
            root=root,
            metadata=document_metadata or {},
            reference_definitions=self._extract_reference_definitions(ast),
        )

    def _build_section(
        self,
        node: dict[str, Any],
        locator: _SourceLocator,
        section_stack: list[SectionNode],
    ) -> SectionNode:
        level = int(node.get("level", 1))
        title_inlines = self._normalize_inlines(node.get("children", []))
        title = self._render_inlines(title_inlines).strip()
        line_number = locator.find_heading(level, title)

        while section_stack and section_stack[-1].level >= level:
            section_stack.pop()
        parent = section_stack[-1]
        return SectionNode(
            level=level,
            title=title,
            path=(*parent.path, (level, title)),
            index=len(parent.children),
            start_line=line_number,
            title_inlines=title_inlines,
        )

    def _build_block(
        self,
        node: dict[str, Any],
        *,
        locator: _SourceLocator | None = None,
    ) -> MarkdownBlock | None:
        kind = self._classify_element(node)
        children = [
            child_block
            for child in self._iter_children(node)
            if isinstance(child, dict) and child.get("element") != "blank_line"
            if (child_block := self._build_block(child)) is not None
        ]
        inlines = (
            self._normalize_inlines(node.get("children", []))
            if self._supports_inlines(kind)
            else []
        )
        text = self._render_block(node, children=children, inlines=inlines).strip()
        if not text:
            return None

        start_line = None
        end_line = None
        literal = self._extract_literal_text(node).rstrip("\n")
        if locator is not None:
            start_line, end_line = locator.find_block(
                kind=kind,
                block_text=text,
                literal=literal,
            )

        return MarkdownBlock(
            kind=kind,
            text=text,
            start_line=start_line,
            end_line=end_line,
            children=children,
            inlines=inlines,
            attrs=self._extract_block_attrs(node),
        )

    def _parse_to_ast(self, text: str) -> dict[str, Any]:
        try:
            from marko import Markdown
            from marko.ast_renderer import ASTRenderer
        except ImportError as exc:
            raise RuntimeError(
                "marko is not installed. Install dependencies with `uv sync --extra parsers`."
            ) from exc

        ast = Markdown(renderer=ASTRenderer).convert(text)
        if not isinstance(ast, dict):
            raise TypeError("marko AST renderer returned an unexpected payload")
        return ast

    def _extract_reference_definitions(self, ast: dict[str, Any]) -> dict[str, dict[str, str]]:
        definitions: dict[str, dict[str, str]] = {}
        for child in ast.get("children", []):
            if not isinstance(child, dict) or child.get("element") != "link_ref_def":
                continue
            label = str(child.get("label", "")).strip()
            if not label:
                continue
            definitions[label] = {
                "destination": str(child.get("dest", "")),
                "title": self._normalize_reference_title(child.get("title")),
            }
        return definitions

    def _normalize_reference_title(self, title: Any) -> str:
        value = str(title or "").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            return value[1:-1]
        return value

    def _classify_element(self, node: dict[str, Any]) -> str:
        element = str(node.get("element", "paragraph"))
        if element == "quote":
            return "blockquote"
        if element == "fenced_code":
            return "code_fence"
        if element == "link_ref_def":
            return "link_reference_definition"
        if element in {
            "paragraph",
            "list",
            "list_item",
            "code_block",
            "html_block",
            "thematic_break",
        }:
            return element
        return "paragraph"

    def _extract_block_attrs(self, node: dict[str, Any]) -> dict[str, Any]:
        kind = self._classify_element(node)
        attrs: dict[str, Any] = {}
        if kind == "list":
            attrs["ordered"] = bool(node.get("ordered"))
            attrs["start"] = int(node.get("start") or 1)
            attrs["tight"] = bool(node.get("tight"))
            attrs["bullet"] = str(node.get("bullet") or ("1." if attrs["ordered"] else "-"))
        elif kind == "code_fence":
            attrs["language"] = str(node.get("lang") or "")
            attrs["info"] = " ".join(
                part for part in (str(node.get("lang") or ""), str(node.get("extra") or "")) if part
            ).strip()
            attrs["literal"] = self._extract_literal_text(node).rstrip("\n")
        elif kind in ["code_block", "html_block"]:
            attrs["literal"] = self._extract_literal_text(node).rstrip("\n")
        elif kind == "link_reference_definition":
            attrs["label"] = str(node.get("label") or "")
            attrs["destination"] = str(node.get("dest") or "")
            attrs["title"] = self._normalize_reference_title(node.get("title"))
        return attrs

    def _supports_inlines(self, kind: str) -> bool:
        return kind in {"paragraph", "link_reference_definition"}

    def _render_block(
        self,
        node: dict[str, Any],
        *,
        children: list[MarkdownBlock],
        inlines: list[MarkdownInline],
    ) -> str:
        kind = self._classify_element(node)

        if kind == "paragraph":
            return self._render_inlines(inlines)
        if kind == "blockquote":
            content = "\n\n".join(child.text for child in children if child.text)
            return "\n".join(f"> {line}" if line else ">" for line in content.splitlines())
        if kind == "list":
            return "\n".join(child.text for child in children if child.text)
        if kind == "list_item":
            ordered = False
            start = 1
            bullet = "-"
            if isinstance(node.get("_parent"), dict):
                ordered = bool(node["_parent"].get("ordered"))
                start = int(node["_parent"].get("start") or 1)
            if ordered:
                bullet = f"{start + int(node.get('_list_index', 0))}."
            content = "\n\n".join(child.text for child in children if child.text).strip()
            if not content:
                return bullet
            lines = content.splitlines()
            rendered_lines = [f"{bullet} {lines[0]}"]
            rendered_lines.extend(f"  {line}" if line else "" for line in lines[1:])
            return "\n".join(rendered_lines)
        if kind == "code_fence":
            info = " ".join(
                part for part in (str(node.get("lang") or ""), str(node.get("extra") or "")) if part
            ).strip()
            body = self._extract_literal_text(node).rstrip("\n")
            fence = f"```{info}".rstrip()
            return f"{fence}\n{body}\n```"
        if kind == "code_block":
            body = self._extract_literal_text(node).rstrip("\n")
            return f"```\n{body}\n```"
        if kind == "html_block":
            return self._extract_literal_text(node).strip()
        if kind == "thematic_break":
            return "---"
        if kind == "link_reference_definition":
            label = str(node.get("label") or "")
            destination = str(node.get("dest") or "")
            title = self._normalize_reference_title(node.get("title"))
            title_suffix = f' "{title}"' if title else ""
            return f"[{label}]: {destination}{title_suffix}"

        return "\n\n".join(child.text for child in children if child.text)

    def _normalize_inlines(self, nodes: Any) -> list[MarkdownInline]:
        if isinstance(nodes, list):
            raw_nodes = nodes
        elif isinstance(nodes, dict):
            raw_nodes = [nodes]
        else:
            return []

        normalized: list[MarkdownInline] = []
        for node in raw_nodes:
            inline = self._normalize_inline(node)
            if inline is not None:
                normalized.append(inline)
        return normalized

    def _normalize_inline(self, node: Any) -> MarkdownInline | None:
        if isinstance(node, str):
            return MarkdownInline(kind="text", text=node)
        if not isinstance(node, dict):
            return None

        element = str(node.get("element", "text"))
        if element == "raw_text":
            return MarkdownInline(kind="text", text=str(node.get("children", "")))
        if element == "code_span":
            return MarkdownInline(
                kind="code_span",
                text=self._extract_literal_text(node),
                attrs={"literal": self._extract_literal_text(node)},
            )
        if element in {"emphasis", "strong_emphasis"}:
            return MarkdownInline(
                kind="emphasis" if element == "emphasis" else "strong",
                children=self._normalize_inlines(node.get("children", [])),
            )
        if element in {"link", "image", "auto_link"}:
            kind = "autolink" if element == "auto_link" else element
            return MarkdownInline(
                kind=kind,
                children=self._normalize_inlines(node.get("children", [])),
                attrs={
                    "destination": str(node.get("dest", "")),
                    "title": str(node.get("title") or ""),
                },
            )
        if element == "inline_html":
            return MarkdownInline(kind="inline_html", text=self._extract_literal_text(node))
        if element == "line_break":
            soft = bool(node.get("soft", False))
            return MarkdownInline(kind="soft_break" if soft else "hard_break", text="\n")

        return MarkdownInline(
            kind=element,
            text=self._extract_literal_text(node),
            children=self._normalize_inlines(node.get("children", [])),
        )

    def _render_inlines(self, inlines: list[MarkdownInline]) -> str:
        return "".join(self._render_inline(inline) for inline in inlines)

    def _render_inline(self, node: MarkdownInline) -> str:
        if node.kind == "text":
            return node.text
        if node.kind == "code_span":
            return f"`{node.attrs.get('literal', node.text)}`"
        if node.kind == "emphasis":
            return f"*{self._render_inlines(node.children)}*"
        if node.kind == "strong":
            return f"**{self._render_inlines(node.children)}**"
        if node.kind == "link":
            title = str(node.attrs.get("title") or "").strip()
            title_suffix = f' "{title}"' if title else ""
            return f"[{self._render_inlines(node.children)}]({node.attrs.get('destination', '')}{title_suffix})"
        if node.kind == "image":
            title = str(node.attrs.get("title") or "").strip()
            title_suffix = f' "{title}"' if title else ""
            return f"![{self._render_inlines(node.children)}]({node.attrs.get('destination', '')}{title_suffix})"
        if node.kind == "autolink":
            return f"<{node.attrs.get('destination', self._render_inlines(node.children))}>"
        if node.kind == "inline_html":
            return node.text
        if node.kind in {"soft_break", "hard_break"}:
            return "\n"
        if node.children:
            return self._render_inlines(node.children)
        return node.text

    def _extract_literal_text(self, node: Any) -> str:
        if isinstance(node, str):
            return node
        if isinstance(node, list):
            return "".join(self._extract_literal_text(child) for child in node)
        if not isinstance(node, dict):
            return ""

        if "body" in node and isinstance(node["body"], str):
            return node["body"]

        children = node.get("children", [])
        if isinstance(children, str):
            return children
        return "".join(self._extract_literal_text(child) for child in self._iter_children(node))

    def _iter_children(self, node: Any) -> list[Any]:
        if not isinstance(node, dict):
            return []
        children = node.get("children", [])
        if isinstance(children, list):
            prepared: list[Any] = []
            for index, child in enumerate(children):
                if isinstance(child, dict):
                    child["_parent"] = node
                    child["_list_index"] = index
                prepared.append(child)
            return prepared
        if children in {"", None}:
            return []
        return [children]


class MarkdownParser(CommonMarkASTParser):
    """Default parser that normalizes CommonMark into lumberjack's internal AST."""


def create_parser(name: str) -> MarkdownParserProtocol:
    print(f"Resolving parser for: {name}")
    return CommonMarkASTParser()
