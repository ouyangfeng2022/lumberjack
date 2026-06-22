"""HTML document parser producing the shared ``DocumentAST`` model."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser as _StdlibHTMLParser
from typing import Any, ClassVar

from ...models import DocumentAST, MarkdownBlock, MarkdownInline, SectionNode


def _clean_text(text: str) -> str:
    """Collapse HTML text whitespace into a Markdown-like paragraph string."""
    return " ".join(text.split())


def _line_offsets(source: str) -> list[int]:
    """Return the absolute offset where each 1-based line starts."""
    offsets = [0]
    offset = 0
    for line in source.splitlines(keepends=True):
        offset += len(line)
        offsets.append(offset)
    return offsets


def _attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {name.lower(): value or "" for name, value in attrs}


@dataclass(slots=True)
class _TextCollector:
    kind: str
    start_line: int | None
    text_parts: list[str] = field(default_factory=list)
    inlines: list[MarkdownInline] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)

    def add_text(self, text: str, inline_kind: str = "text") -> None:
        if not text:
            return
        self.text_parts.append(text)
        self.inlines.append(MarkdownInline(kind=inline_kind, text=text))

    def rendered_text(self) -> str:
        return _clean_text("".join(self.text_parts))

    def literal_text(self) -> str:
        return "".join(self.text_parts).strip("\n")


@dataclass(slots=True)
class _ListItem:
    text: str
    start_line: int | None
    end_line: int | None
    inlines: tuple[MarkdownInline, ...]


@dataclass(slots=True)
class _ListCollector:
    ordered: bool
    start_line: int | None
    items: list[_ListItem] = field(default_factory=list)


@dataclass(slots=True)
class _TableCollector:
    start_offset: int
    start_line: int | None
    depth: int = 1


class _HTMLDocumentBuilder(_StdlibHTMLParser):
    """Event parser that normalizes HTML into the shared DocumentAST model."""

    _BLOCK_TAGS: ClassVar[frozenset[str]] = frozenset({"p", "pre", "blockquote"})
    _HEADING_TAGS: ClassVar[frozenset[str]] = frozenset(
        {"h1", "h2", "h3", "h4", "h5", "h6"}
    )
    _INLINE_KIND_BY_TAG: ClassVar[dict[str, str]] = {
        "strong": "strong",
        "b": "strong",
        "em": "emphasis",
        "i": "emphasis",
        "code": "code_span",
        "a": "link",
    }

    def __init__(
        self,
        *,
        source: str,
        document_title: str | None,
        document_metadata: dict[str, object],
        max_heading_level: int | None,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._source = source
        self._line_offsets = _line_offsets(source)
        self._document_title = document_title
        self._metadata = dict(document_metadata)
        self._max_heading_level = max_heading_level
        self._root = SectionNode(level=0, title="")
        self._section_stack: list[SectionNode] = [self._root]
        self._heading: _TextCollector | None = None
        self._block: _TextCollector | None = None
        self._list_stack: list[_ListCollector] = []
        self._list_item: _TextCollector | None = None
        self._table_stack: list[_TableCollector] = []
        self._title_parts: list[str] = []
        self._collect_title = False
        self._skip_depth = 0
        self._head_depth = 0
        self._body_seen = False
        self._inline_stack: list[str] = []

    def build(self) -> DocumentAST:
        self.feed(self._source)
        self.close()
        self._close_block(self.getpos()[0])
        final_title = self._resolve_document_title()
        self._root.title = final_title
        return DocumentAST(
            title=final_title,
            source=self._source,
            root=self._root,
            metadata=self._metadata,
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        line, column = self.getpos()
        if tag == "head":
            self._head_depth += 1
            return
        if tag == "body":
            self._body_seen = True
            return
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._collect_title = True
            self._title_parts = []
            return
        if tag == "meta":
            self._capture_meta(attrs)
            return
        if self._skip_depth or self._head_depth:
            return

        if tag == "table":
            if self._table_stack:
                self._table_stack[-1].depth += 1
            else:
                self._close_block(line)
                self._table_stack.append(
                    _TableCollector(
                        start_offset=self._absolute_offset(line, column),
                        start_line=line,
                    )
                )
            return
        if self._table_stack:
            return

        if tag in self._HEADING_TAGS:
            self._close_block(line)
            self._heading = _TextCollector(
                kind=tag,
                start_line=line,
                attrs={"level": int(tag[1])},
            )
            return
        if tag in {"ul", "ol"}:
            self._close_block(line)
            self._list_stack.append(
                _ListCollector(ordered=tag == "ol", start_line=line)
            )
            return
        if tag == "li":
            self._list_item = _TextCollector(kind="list_item", start_line=line)
            return
        if tag in self._BLOCK_TAGS and self._list_item is None:
            self._close_block(line)
            kind_by_tag = {
                "blockquote": "blockquote",
                "p": "paragraph",
                "pre": "code_block",
            }
            kind = kind_by_tag[tag]
            self._block = _TextCollector(kind=kind, start_line=line)
            return
        if tag == "br":
            self._add_text("\n")
            return
        if tag == "img":
            alt = _attrs_dict(attrs).get("alt", "")
            if alt:
                self._add_text(alt, "image")
            return
        if tag in self._INLINE_KIND_BY_TAG:
            self._inline_stack.append(self._INLINE_KIND_BY_TAG[tag])

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        line, column = self.getpos()
        if tag == "head":
            self._head_depth = max(0, self._head_depth - 1)
            return
        if tag in {"script", "style"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._collect_title = False
            title = _clean_text("".join(self._title_parts))
            if title:
                self._metadata.setdefault("title", title)
            return
        if self._skip_depth or self._head_depth:
            return

        if self._table_stack:
            if tag == "table":
                table = self._table_stack[-1]
                table.depth -= 1
                if table.depth == 0:
                    self._table_stack.pop()
                    self._add_table_block(table, self._end_tag_offset(line, column))
            return

        if self._heading is not None and tag == self._heading.kind:
            self._add_heading_or_paragraph(line)
            return
        if self._block is not None and tag in self._BLOCK_TAGS:
            self._close_block(line)
            return
        if self._list_item is not None and tag == "li":
            self._close_list_item(line)
            return
        if tag in {"ul", "ol"}:
            self._close_list(line)
            return
        if tag in self._INLINE_KIND_BY_TAG and self._inline_stack:
            self._inline_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._collect_title:
            self._title_parts.append(data)
            return
        if self._skip_depth or self._head_depth or self._table_stack:
            return
        self._add_text(data)

    def _capture_meta(self, attrs: list[tuple[str, str | None]]) -> None:
        attrs_by_name = _attrs_dict(attrs)
        key = attrs_by_name.get("name") or attrs_by_name.get("property")
        content = attrs_by_name.get("content")
        if key and content:
            self._metadata.setdefault(key.lower(), content)

    def _add_text(self, text: str, inline_kind: str | None = None) -> None:
        if not text:
            return
        kind = inline_kind or (self._inline_stack[-1] if self._inline_stack else "text")
        if self._heading is not None:
            self._heading.add_text(text, kind)
        elif self._list_item is not None:
            self._list_item.add_text(text, kind)
        elif self._block is not None:
            self._block.add_text(text, kind)
        elif text.strip() and self._body_seen:
            line = self.getpos()[0]
            self._block = _TextCollector(kind="paragraph", start_line=line)
            self._block.add_text(text, kind)

    def _add_heading_or_paragraph(self, end_line: int) -> None:
        if self._heading is None:
            return
        title = self._heading.rendered_text()
        if not title:
            self._heading = None
            return
        level = int(self._heading.attrs["level"])
        if self._max_heading_level is not None and level > self._max_heading_level:
            self._section_stack[-1].add_block(
                MarkdownBlock(
                    kind="paragraph",
                    text=title,
                    start_line=self._heading.start_line,
                    end_line=end_line,
                    inlines=tuple(self._heading.inlines),
                )
            )
            self._heading = None
            return

        while self._section_stack and self._section_stack[-1].level >= level:
            self._section_stack.pop()
        parent = self._section_stack[-1]
        section = SectionNode(
            level=level,
            title=title,
            path=(*parent.path, (level, title)),
            index=len(parent.children),
            start_line=self._heading.start_line,
            title_inlines=tuple(self._heading.inlines),
        )
        parent.add_child(section)
        self._section_stack.append(section)
        self._heading = None

    def _close_block(self, end_line: int) -> None:
        if self._block is None:
            return
        text = self._block.rendered_text()
        if text:
            kind = self._block.kind
            if kind == "blockquote":
                text = "\n".join(f"> {line}" for line in text.splitlines())
            if kind == "code_block":
                literal = self._block.literal_text()
                text = f"```\n{literal}\n```"
                self._block.attrs["literal"] = literal
            self._section_stack[-1].add_block(
                MarkdownBlock(
                    kind=kind,
                    text=text,
                    start_line=self._block.start_line,
                    end_line=end_line,
                    inlines=tuple(self._block.inlines),
                    attrs=self._block.attrs,
                )
            )
        self._block = None

    def _close_list_item(self, end_line: int) -> None:
        if self._list_item is None:
            return
        text = self._list_item.rendered_text()
        if text and self._list_stack:
            self._list_stack[-1].items.append(
                _ListItem(
                    text=text,
                    start_line=self._list_item.start_line,
                    end_line=end_line,
                    inlines=tuple(self._list_item.inlines),
                )
            )
        self._list_item = None

    def _close_list(self, end_line: int) -> None:
        if not self._list_stack:
            return
        list_block = self._list_stack.pop()
        if not list_block.items:
            return
        children = tuple(
            MarkdownBlock(
                kind="list_item",
                text=item.text,
                start_line=item.start_line,
                end_line=item.end_line,
                inlines=item.inlines,
            )
            for item in list_block.items
        )
        marker = "1." if list_block.ordered else "-"
        text = "\n".join(f"{marker} {item.text}" for item in list_block.items)
        self._section_stack[-1].add_block(
            MarkdownBlock(
                kind="list",
                text=text,
                start_line=list_block.start_line,
                end_line=end_line,
                children=children,
                attrs={"ordered": list_block.ordered},
            )
        )

    def _add_table_block(self, table: _TableCollector, end_offset: int) -> None:
        table_html = self._source[table.start_offset : end_offset].strip()
        if not table_html:
            return
        self._section_stack[-1].add_block(
            MarkdownBlock(
                kind="html_table",
                text=table_html,
                start_line=table.start_line,
                end_line=self.getpos()[0],
                attrs={"literal": table_html},
            )
        )

    def _resolve_document_title(self) -> str:
        if self._document_title:
            return self._document_title
        metadata_title = self._metadata.get("title")
        if isinstance(metadata_title, str) and metadata_title.strip():
            return metadata_title.strip()
        for section in self._root.children:
            if section.level == 1 and section.title:
                return section.title
        return "Anonymous"

    def _absolute_offset(self, line: int, column: int) -> int:
        if line <= 0:
            return column
        if line - 1 >= len(self._line_offsets):
            return len(self._source)
        return min(len(self._source), self._line_offsets[line - 1] + column)

    def _end_tag_offset(self, line: int, column: int) -> int:
        start = self._absolute_offset(line, column)
        tag_end = self._source.find(">", start)
        return len(self._source) if tag_end == -1 else tag_end + 1


class HTMLParser:
    """Parse HTML documents into the shared ``DocumentAST`` model.

    The parser mirrors the public parser shape used by Markdown and DOCX:
    it exposes ``block_kinds`` and returns a heading-tree ``DocumentAST`` so
    the existing splitters can operate on HTML input without a separate path.
    """

    _BLOCK_KINDS: frozenset[str] = frozenset(
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
        return self._BLOCK_KINDS

    def parse(
        self,
        text: str,
        *,
        document_title: str | None = None,
        document_metadata: dict[str, object] | None = None,
        max_heading_level: int | None = None,
    ) -> DocumentAST:
        """Parse raw HTML text into a ``DocumentAST``.

        Args:
            text: Raw HTML source.
            document_title: Optional override for the document title.
            document_metadata: Optional metadata dict merged into the result.
            max_heading_level: Maximum heading level to parse as sections.
                Headings deeper than this level are treated as paragraph blocks.
        """
        builder = _HTMLDocumentBuilder(
            source=text,
            document_title=document_title,
            document_metadata=document_metadata or {},
            max_heading_level=max_heading_level,
        )
        return builder.build()
