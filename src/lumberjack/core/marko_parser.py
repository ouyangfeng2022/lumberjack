from __future__ import annotations

import re
from typing import Any

from ..base.interfaces import MarkdownParserProtocol
from ..models import DocumentAST, MarkdownBlock, SectionNode

ATX_HEADING_RE = re.compile(r"^[ ]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")


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

    def find_block(self, block_text: str) -> tuple[int | None, int | None]:
        if not block_text.strip():
            return (None, None)

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


class MarkoMarkdownParser(MarkdownParserProtocol):
    """Build the internal AST from Marko's CommonMark parser."""

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
            if not isinstance(child, dict):
                continue

            if child.get("element") == "heading":
                level = int(child.get("level", 1))
                title = self._render_inline(child).strip()
                line_number = locator.find_heading(level, title)
                while section_stack and section_stack[-1].level >= level:
                    section_stack.pop()
                parent = section_stack[-1]
                section = SectionNode(
                    level=level,
                    title=title,
                    path=(*parent.path, (level, title)),
                    index=len(parent.children),
                    start_line=line_number,
                )
                parent.add_child(section)
                section_stack.append(section)
                continue

            block_text = self._render_block(child).strip()
            if not block_text:
                continue
            start_line, end_line = locator.find_block(block_text)

            section_stack[-1].add_block(
                MarkdownBlock(
                    kind=self._classify_element(child),
                    text=block_text,
                    start_line=start_line,
                    end_line=end_line,
                )
            )
        return DocumentAST(
            title=document_title,
            source=text,
            root=root,
            metadata=document_metadata or {},
        )

    def _parse_to_ast(self, text: str) -> dict[str, Any]:
        try:
            from marko import Markdown
            from marko.ast_renderer import ASTRenderer
        except ImportError as exc:
            raise RuntimeError(
                "marko is not installed. Install with `pip install lumberjack[parsers]`."
            ) from exc

        ast = Markdown(renderer=ASTRenderer).convert(text)
        if not isinstance(ast, dict):
            raise TypeError("marko AST renderer returned an unexpected payload")
        return ast

    def _classify_element(self, node: dict[str, Any]) -> str:
        element = node.get("element")
        mapping = {
            "paragraph": "paragraph",
            "list": "list",
            "quote": "blockquote",
            "fenced_code": "code_fence",
            "code_block": "code_fence",
            "html_block": "html",
            "thematic_break": "thematic_break",
            "table": "table",
        }
        return mapping.get(str(element), "paragraph")

    def _render_block(self, node: Any) -> str:
        if isinstance(node, str):
            return node
        if not isinstance(node, dict):
            return ""

        element = node.get("element")

        if element == "blank_line":
            return ""
        if element == "paragraph":
            return self._render_inline(node).strip()
        if element == "quote":
            content = "\n\n".join(
                rendered
                for child in node.get("children", [])
                if (rendered := self._render_block(child))
            )
            return "\n".join(f"> {line}" if line else ">" for line in content.splitlines()).strip()
        if element == "fenced_code":
            lang = str(node.get("lang") or "").strip()
            extra = str(node.get("extra") or "").strip()
            info = " ".join(part for part in [lang, extra] if part).strip()
            body = self._extract_literal_text(node).rstrip("\n")
            fence = f"```{info}".rstrip()
            return f"{fence}\n{body}\n```"
        if element == "code_block":
            body = self._extract_literal_text(node).rstrip("\n")
            return f"```\n{body}\n```"
        if element == "html_block":
            return self._extract_literal_text(node).strip()
        if element == "thematic_break":
            return "---"
        if element == "list":
            return self._render_list(node)
        if element == "list_item":
            return self._render_list_item(node, bullet="-")

        content = "\n\n".join(
            rendered
            for child in node.get("children", [])
            if (rendered := self._render_block(child))
        )
        if content:
            return content
        return self._render_inline(node).strip()

    def _render_list(self, node: dict[str, Any]) -> str:
        ordered = bool(node.get("ordered"))
        start = int(node.get("start") or 1)
        items: list[str] = []

        for index, child in enumerate(node.get("children", []), start=start):
            bullet = f"{index}." if ordered else "-"
            items.append(self._render_list_item(child, bullet=bullet))

        return "\n".join(item for item in items if item).strip()

    def _render_list_item(self, node: Any, *, bullet: str) -> str:
        content = "\n\n".join(
            rendered
            for child in self._iter_children(node)
            if (rendered := self._render_block(child))
        ).strip()
        if not content:
            return bullet

        lines = content.splitlines()
        rendered_lines = [f"{bullet} {lines[0]}"]
        rendered_lines.extend(f"  {line}" if line else "" for line in lines[1:])
        return "\n".join(rendered_lines)

    def _render_inline(self, node: Any) -> str:
        if isinstance(node, str):
            return node
        if isinstance(node, list):
            return "".join(self._render_inline(child) for child in node)
        if not isinstance(node, dict):
            return ""

        element = node.get("element")

        if element in {"raw_text", "literal", "text"}:
            return str(node.get("children", ""))
        if element in {"line_break", "soft_break"}:
            return "\n"
        if element == "code_span":
            return f"`{self._extract_literal_text(node)}`"
        if element == "emphasis":
            return f"*{self._render_inline(node.get('children', []))}*"
        if element == "strong_emphasis":
            return f"**{self._render_inline(node.get('children', []))}**"
        if element == "link":
            label = self._render_inline(node.get("children", []))
            destination = str(node.get("dest", ""))
            title = str(node.get("title", "")).strip()
            title_suffix = f' "{title}"' if title else ""
            return f"[{label}]({destination}{title_suffix})"
        if element == "image":
            alt = self._render_inline(node.get("children", []))
            destination = str(node.get("dest", ""))
            title = str(node.get("title", "")).strip()
            title_suffix = f' "{title}"' if title else ""
            return f"![{alt}]({destination}{title_suffix})"

        return "".join(self._render_inline(child) for child in self._iter_children(node))

    def _extract_literal_text(self, node: Any) -> str:
        if isinstance(node, str):
            return node
        if isinstance(node, list):
            return "".join(self._extract_literal_text(child) for child in node)
        if not isinstance(node, dict):
            return ""

        children = node.get("children", [])
        if isinstance(children, str):
            return children
        return "".join(self._extract_literal_text(child) for child in self._iter_children(node))

    def _iter_children(self, node: Any) -> list[Any]:
        if not isinstance(node, dict):
            return []
        children = node.get("children", [])
        if isinstance(children, list):
            return children
        if children in {"", None}:
            return []
        return [children]
