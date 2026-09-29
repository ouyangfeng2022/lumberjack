from __future__ import annotations

import sys

import pytest

from lumberjack.models import Document
from lumberjack.parser import AutoParser, PdfParser


def _pdf(*pages: tuple[str, ...]) -> bytes:
    pages = pages or ((),)
    page_numbers = tuple(range(4, 4 + len(pages)))
    content_numbers = tuple(range(4 + len(pages), 4 + 2 * len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            b"<< /Type /Pages /Kids ["
            + b" ".join(f"{number} 0 R".encode() for number in page_numbers)
            + f"] /Count {len(pages)} >>".encode()
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for page_number, content_number in zip(page_numbers, content_numbers, strict=True):
        del page_number
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents "
            + f"{content_number} 0 R >>".encode()
        )
    for lines in pages:
        commands = [b"BT", b"/F1 18 Tf", b"72 720 Td"]
        for index, line in enumerate(lines):
            if index:
                commands.append(b"0 -28 Td")
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({escaped}) Tj".encode())
        commands.append(b"ET")
        content = b"\n".join(commands)
        objects.append(
            b"<< /Length "
            + str(len(content)).encode()
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    pdf.extend(b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:]))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(pdf)


@pytest.mark.parametrize(
    "pages",
    [
        (("Hello PDF",),),
        (("First line", "Second line"),),
        (("Parentheses (stay)",),),
        (("Slash \\ stays",),),
        (("Alpha",), ("Beta",)),
        (("Page one",), ("Page two",), ("Page three",)),
        (("A-1", "A-2"), ("B-1", "B-2")),
        (("Release 0.5.1",),),
    ],
)
def test_pdf_parser_recalls_visible_text(pages: tuple[tuple[str, ...], ...]) -> None:
    tree = PdfParser().parse(_pdf(*pages), document_title="Report")

    assert tree.title == "Report"
    for line in (line for page in pages for line in page):
        assert line in tree.source


def test_auto_parser_detects_pdf_magic() -> None:
    tree = AutoParser().parse(_pdf(("Hello PDF",)))

    assert [block.text for block in tree.root.blocks] == ["Hello PDF"]


def test_auto_parser_detects_pdf_suffix() -> None:
    tree = AutoParser().parse(Document(_pdf(("Hello PDF",)), source_path="report.pdf"))

    assert [block.text for block in tree.root.blocks] == ["Hello PDF"]


def test_pdf_parser_preserves_metadata_and_source_path() -> None:
    tree = PdfParser().parse(
        Document(
            _pdf(("Hello PDF",)),
            format="pdf",
            document_title="Report",
            metadata_overrides={"owner": "Ada"},
            source_path="reports/report.pdf",
        )
    )

    assert tree.metadata == {"owner": "Ada"}
    assert tree.source_path == "reports/report.pdf"


def test_pdf_parser_rejects_no_text_layer() -> None:
    with pytest.raises(ValueError, match="MinerU or PaddleOCR"):
        PdfParser().parse(_pdf())


def test_pdf_parser_rejects_truncated_pdf() -> None:
    with pytest.raises(ValueError, match="Invalid or unreadable PDF"):
        PdfParser().parse(b"%PDF-1.4\ntruncated")


def test_pdf_parser_reports_encrypted_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    def encrypted(_data: object) -> None:
        raise PDFPasswordIncorrect("password required")

    monkeypatch.setattr("pdfplumber.open", encrypted)
    with pytest.raises(ValueError, match="Encrypted PDF"):
        PdfParser().parse(_pdf(("Secret",)))


def test_pdf_parser_explains_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "markitdown", None)
    with pytest.raises(RuntimeError, match=r"lumberjack-py\[pdf\]"):
        PdfParser().parse(_pdf(("Hello PDF",)))
