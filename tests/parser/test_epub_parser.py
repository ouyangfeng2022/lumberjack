from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from lumberjack import Lumberjack
from lumberjack.parser import AutoParser, EpubParser


def _epub() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>'
            "</container>",
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<metadata><dc:title>Example Book</dc:title></metadata>"
            '<manifest><item id="one" href="one.xhtml"/>'
            '<item id="two" href="two.xhtml"/></manifest>'
            '<spine><itemref idref="two"/><itemref idref="one"/></spine>'
            "</package>",
        )
        archive.writestr("OEBPS/one.xhtml", "<h1>First</h1><p>First body</p>")
        archive.writestr("OEBPS/two.xhtml", "<h1>Second</h1><p>Second body</p>")
    return output.getvalue()


def test_epub_spine_order_headings_and_chunk_provenance() -> None:
    data = _epub()
    tree = EpubParser().parse(data, source_path="book.epub")
    result = Lumberjack().saw(data, format="epub", source_path="book.epub")

    assert tree.title == "Example Book"
    assert [section.title for section in tree.root.children] == ["Second", "First"]
    assert [section.blocks[0].text for section in tree.root.children] == [
        "Second body",
        "First body",
    ]
    assert [
        section.blocks[0].source_locations[0].element_id
        for section in tree.root.children
    ] == [
        "OEBPS/two.xhtml",
        "OEBPS/one.xhtml",
    ]
    assert {
        location.element_id
        for chunk in result.chunks
        for location in chunk.source_locations
    } == {
        "OEBPS/two.xhtml",
        "OEBPS/one.xhtml",
    }


def test_auto_parser_detects_epub_bytes_and_suffix() -> None:
    assert AutoParser().parse(_epub()).title == "Example Book"
    assert AutoParser().parse(_epub(), source_path="book.epub").title == "Example Book"


def test_epub_rejects_corrupt_archive() -> None:
    with pytest.raises(ValueError, match="Invalid or unreadable EPUB"):
        EpubParser().parse(b"PK\x03\x04broken")
