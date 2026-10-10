"""EPUB spine parsing using the existing HTML parser."""

from __future__ import annotations

import posixpath
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urldefrag
from zipfile import BadZipFile, ZipFile

from ..._internal.xml_safe import parse_untrusted_xml
from ...models import DocTree, Document, DocumentBlock, SectionNode, SourceLocation
from ..builder import DocTreeBuilder
from ..html import HTMLParser

_MAX_ENTRY_BYTES = 64 * 1024 * 1024


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class EpubParser:
    """Read EPUB XHTML chapters in spine order with entry provenance."""

    block_kinds = HTMLParser().block_kinds

    def parse(
        self,
        document: Document | bytes,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        if not isinstance(document, Document):
            document = Document(
                document,
                format="epub",
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        if not isinstance(document.source, bytes | bytearray):
            raise TypeError("EpubParser.parse expects Document[bytes]")
        try:
            with ZipFile(BytesIO(bytes(document.source))) as archive:
                if self._read(archive, "mimetype") != b"application/epub+zip":
                    raise ValueError("Invalid EPUB: unexpected package mimetype")
                container = parse_untrusted_xml(
                    self._read(archive, "META-INF/container.xml")
                )
                opf_path = next(
                    node.attrib["full-path"]
                    for node in container.iter()
                    if _local_name(node.tag) == "rootfile"
                )
                package = parse_untrusted_xml(self._read(archive, opf_path))
                manifest = {
                    node.attrib["id"]: node.attrib["href"]
                    for node in package.iter()
                    if _local_name(node.tag) == "item"
                }
                spine = [
                    node.attrib["idref"]
                    for node in package.iter()
                    if _local_name(node.tag) == "itemref"
                    and node.attrib.get("linear", "yes") != "no"
                ]
                title = next(
                    (
                        node.text.strip()
                        for node in package.iter()
                        if _local_name(node.tag) == "title" and node.text
                    ),
                    "Anonymous",
                )
                builder = DocTreeBuilder(
                    title=document.document_title or title,
                    source_path=document.source_path,
                    metadata=document.metadata_overrides,
                    block_kinds=self.block_kinds,
                )
                source_parts: list[str] = []
                for item_id in spine:
                    href = manifest[item_id]
                    entry = posixpath.normpath(
                        posixpath.join(
                            posixpath.dirname(opf_path), unquote(urldefrag(href)[0])
                        )
                    )
                    if entry.startswith("../") or entry.startswith("/"):
                        raise ValueError(f"EPUB spine entry escapes archive: {href}")
                    html = self._read(archive, entry).decode("utf-8-sig")
                    chapter = HTMLParser().parse(html)
                    location = SourceLocation(
                        source=str(document.source_path)
                        if document.source_path is not None
                        else None,
                        element_id=entry,
                    )
                    chapter_title = (
                        chapter.root.children[0].title
                        if chapter.root.children
                        else Path(entry).stem
                    )
                    builder.add_section(1, chapter_title, location=location)
                    self._add_blocks(builder, chapter.root.blocks, location)
                    for index, section in enumerate(chapter.root.children):
                        if index == 0 and section.title == chapter_title:
                            self._add_blocks(builder, section.blocks, location)
                            for child in section.children:
                                self._add_section(builder, child, location, 1)
                        else:
                            self._add_section(builder, section, location, 1)
                    source_parts.append(html)
                if not source_parts:
                    raise ValueError("EPUB spine contains no readable chapters")
                tree = builder.build()
                return replace(tree, source="\n\n".join(source_parts))
        except (BadZipFile, KeyError, StopIteration, UnicodeError) as exc:
            raise ValueError(f"Invalid or unreadable EPUB: {exc}") from exc

    @staticmethod
    def _read(archive: ZipFile, name: str) -> bytes:
        info = archive.getinfo(name)
        if info.flag_bits & 1:
            raise ValueError(f"Encrypted EPUB entry is unsupported: {name}")
        if info.file_size > _MAX_ENTRY_BYTES:
            raise ValueError(f"EPUB entry exceeds {_MAX_ENTRY_BYTES} bytes: {name}")
        return archive.read(info)

    @staticmethod
    def _add_blocks(
        builder: DocTreeBuilder, blocks: list[DocumentBlock], location: SourceLocation
    ) -> None:
        for block in blocks:
            builder.add_block(
                block.kind,
                block.text,
                locations=(location,),
                children=block.children,
                inlines=block.inlines,
                attrs=block.attrs,
            )

    @classmethod
    def _add_section(
        cls,
        builder: DocTreeBuilder,
        section: SectionNode,
        location: SourceLocation,
        offset: int,
    ) -> None:
        builder.add_section(
            min(section.level + offset, 6), section.title, location=location
        )
        cls._add_blocks(builder, section.blocks, location)
        for child in section.children:
            cls._add_section(builder, child, location, offset)
