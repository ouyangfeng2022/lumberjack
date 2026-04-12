from __future__ import annotations

import re

from ..base.interfaces import MarkdownParserProtocol
from ..models import DocumentAST, MarkdownBlock, SectionNode

ATX_HEADING_RE = re.compile(r"^[ ]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
OPEN_FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$")


def _classify_block(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith(("> ", ">")):
        return "blockquote"
    if stripped.startswith(("- ", "* ", "+ ")):
        return "list"
    if stripped[:1].isdigit() and ". " in stripped[:4]:
        return "list"
    if stripped.startswith("|"):
        return "table"
    if stripped.startswith("<"):
        return "html"
    if stripped in {"---", "***", "___"}:
        return "thematic_break"
    return "paragraph"


class MarkdownParser(MarkdownParserProtocol):
    """A lightweight markdown parser for section-aware splitting."""

    def parse(self, text: str, *, document_title: str = "document.md") -> DocumentAST:
        root = SectionNode(level=0, title=document_title)
        section_stack: list[SectionNode] = [root]

        current_lines: list[str] = []
        current_kind: str | None = None
        current_start_line: int | None = None
        open_fence: str | None = None
        total_lines = text.splitlines()

        def flush_current_block(end_line: int | None = None) -> None:
            nonlocal current_lines, current_kind, current_start_line
            if not current_lines:
                return
            block_text = "\n".join(current_lines).strip("\n")
            if block_text.strip():
                section_stack[-1].add_block(
                    MarkdownBlock(
                        kind=current_kind or "paragraph",
                        text=block_text,
                        start_line=current_start_line,
                        end_line=end_line,
                    )
                )
            current_lines = []
            current_kind = None
            current_start_line = None

        for line_number, line in enumerate(total_lines, start=1):
            if open_fence is not None:
                current_lines.append(line)
                if line.lstrip().startswith(open_fence):
                    flush_current_block(end_line=line_number)
                    open_fence = None
                continue

            heading_match = ATX_HEADING_RE.match(line)
            if heading_match:
                flush_current_block(end_line=line_number - 1)
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
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

            fence_match = OPEN_FENCE_RE.match(line)
            if fence_match:
                flush_current_block(end_line=line_number - 1)
                current_kind = "code_fence"
                current_lines = [line]
                current_start_line = line_number
                open_fence = fence_match.group(1)
                continue

            if not line.strip():
                flush_current_block(end_line=line_number - 1)
                continue

            if not current_lines:
                current_kind = _classify_block(line)
                current_start_line = line_number
            current_lines.append(line)

        flush_current_block(end_line=len(total_lines))
        return DocumentAST(title=document_title, source=text, root=root)
