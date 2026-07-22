"""Tests for HTML table parsing and splitting."""

from __future__ import annotations

from lumberjack.core.block import BlockSplitter
from lumberjack.core.models import SplitOptions, TableBlockParams
from lumberjack.core.parser.html import HTMLParser
from lumberjack.core.parser.html.table_parser import HTMLTableParser
from lumberjack.core.parser.markdown.parser import MarkdownParser
from lumberjack.core.splitter import create_splitter
from tests.helpers import CharacterTokenizer


def test_html_parser_builds_document_ast_with_sections_and_blocks():
    """HTMLParser should produce the same DocumentAST shape as Markdown/DOCX parsers."""
    parser = HTMLParser()
    html = """<!doctype html>
<html>
  <head>
    <title>Ignored head title</title>
    <meta name="author" content="Ada">
  </head>
  <body>
    <h1>Guide</h1>
    <p>Intro <strong>bold</strong> text.</p>
    <h2>Data</h2>
    <ul><li>First</li><li>Second</li></ul>
    <table><tr><th>Name</th></tr><tr><td>Alice</td></tr></table>
  </body>
</html>"""

    document = parser.parse(html, document_title="guide.html")

    assert document.title == "guide.html"
    assert document.source == html
    assert document.metadata["author"] == "Ada"
    guide = document.root.children[0]
    assert guide.title == "Guide"
    assert guide.path == ((1, "Guide"),)
    assert guide.blocks[0].kind == "paragraph"
    assert guide.blocks[0].text == "Intro bold text."
    data = guide.children[0]
    assert data.title == "Data"
    assert data.blocks[0].kind == "list"
    assert data.blocks[0].text == "- First\n- Second"
    assert data.blocks[1].kind == "html_table"
    assert "<table>" in data.blocks[1].text


def test_html_parser_block_kinds_match_default_block_kinds() -> None:
    parser = HTMLParser()

    assert parser.block_kinds == HTMLParser.default_block_kinds
    assert parser.block_kinds == frozenset(
        {
            "paragraph",
            "blockquote",
            "list",
            "list_item",
            "code_block",
            "html_table",
        }
    )
    assert isinstance(parser.block_kinds, frozenset)


def test_html_splitter_respects_max_heading_level():
    """Heading-depth limiting is applied by the splitter, not the HTML parser."""
    parser = HTMLParser()
    document = parser.parse("<h1>Top</h1><h3>Deep</h3><p>Body</p>")

    top = document.root.children[0]
    assert top.title == "Top"
    assert top.children[0].title == "Deep"

    splitter = create_splitter(
        "sibling",
        CharacterTokenizer(),
        options=SplitOptions(max_tokens=500, max_heading_level=2),
    )
    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ()
    assert chunks[0].section_level == 1
    assert "### Deep" in chunks[0].body


def test_html_parser_preserves_preformatted_text() -> None:
    parser = HTMLParser()

    document = parser.parse("<h1>Code</h1><pre>def f():\n    return 1</pre>")

    code_block = document.root.children[0].blocks[0]
    assert code_block.kind == "code_block"
    assert code_block.text == "```\ndef f():\n    return 1\n```"
    assert code_block.attrs["literal"] == "def f():\n    return 1"


def test_html_table_parser_detects_simple_table():
    """Test that the HTML table parser can detect a simple HTML table."""
    parser = HTMLTableParser()
    html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"

    assert parser.contains_table(html)


def test_html_table_parser_detects_no_table():
    """Test that the HTML table parser correctly identifies content without tables."""
    parser = HTMLTableParser()
    html = "<p>This is just a paragraph with <strong>bold text</strong>.</p>"

    assert not parser.contains_table(html)


def test_html_table_parser_extracts_simple_table():
    """Test extracting a simple HTML table structure."""
    parser = HTMLTableParser()
    html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"

    tables = parser.extract_tables(html)
    assert len(tables) == 1

    table = tables[0]
    assert len(table.headers) == 1
    assert len(table.rows) == 1
    assert table.headers[0].is_header
    assert not table.rows[0].is_header


def test_html_table_parser_with_complex_structure():
    """Test parsing a more complex HTML table with multiple rows."""
    parser = HTMLTableParser()
    html = """<table>
        <caption>Sample Table</caption>
        <tr><th>Name</th><th>Age</th><th>City</th></tr>
        <tr><td>Alice</td><td>30</td><td>New York</td></tr>
        <tr><td>Bob</td><td>25</td><td>Los Angeles</td></tr>
        <tr><td>Charlie</td><td>35</td><td>Chicago</td></tr>
    </table>"""

    tables = parser.extract_tables(html)
    assert len(tables) == 1

    table = tables[0]
    assert table.caption == "Sample Table"
    assert len(table.headers) == 1
    assert len(table.rows) == 3

    # Check header row
    header_row = table.headers[0]
    assert header_row.is_header
    assert len(header_row.cells) == 3
    assert header_row.cells[0].text == "Name"
    assert header_row.cells[1].text == "Age"
    assert header_row.cells[2].text == "City"

    # Check first data row
    data_row = table.rows[0]
    assert not data_row.is_header
    assert len(data_row.cells) == 3
    assert data_row.cells[0].text == "Alice"
    assert data_row.cells[1].text == "30"
    assert data_row.cells[2].text == "New York"


def test_html_table_parser_handles_colspan():
    """Test parsing HTML table with colspan attribute."""
    parser = HTMLTableParser()
    html = (
        '<table><tr><th colspan="2">Name</th></tr><tr><td>A</td><td>B</td></tr></table>'
    )

    tables = parser.extract_tables(html)
    assert len(tables) == 1

    table = tables[0]
    header_row = table.headers[0]
    assert header_row.cells[0].col_span == 2


def test_html_table_parser_handles_rowspan():
    """Test parsing HTML table with rowspan attribute."""
    parser = HTMLTableParser()
    html = '<table><tr><th rowspan="2">X</th><th>A</th></tr><tr><td>B</td></tr></table>'

    tables = parser.extract_tables(html)
    assert len(tables) == 1

    table = tables[0]
    header_row = table.headers[0]
    assert header_row.cells[0].row_span == 2


def test_html_table_parser_preserves_mixed_header_and_data_cells() -> None:
    parser = HTMLTableParser()
    html = "<table><tr><th>Name</th><td>Alice</td></tr></table>"

    tables = parser.extract_tables(html)

    row = tables[0].headers[0]
    assert row.is_header
    assert [cell.text for cell in row.cells] == ["Name", "Alice"]
    assert [cell.is_header for cell in row.cells] == [True, False]


def test_html_table_to_markdown_simple():
    """Test converting a simple HTML table to markdown format."""
    parser = HTMLTableParser()
    html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"

    tables = parser.extract_tables(html)
    markdown = parser.to_markdown_table(tables[0])

    # Check that the markdown table has proper structure
    lines = markdown.strip().split("\n")
    assert len(lines) == 3
    assert lines[0].startswith("|") and lines[0].endswith("|")
    assert lines[1].startswith("|") and lines[1].endswith("|")
    assert "---" in lines[1]  # Delimiter row
    assert lines[2].startswith("|") and lines[2].endswith("|")


def test_html_table_to_markdown_with_caption():
    """Test converting HTML table with caption to markdown format."""
    parser = HTMLTableParser()
    html = (
        "<table><caption>Data</caption><tr><th>A</th></tr><tr><td>1</td></tr></table>"
    )

    tables = parser.extract_tables(html)
    markdown = parser.to_markdown_table(tables[0])

    assert "*Data*" in markdown


def test_text_splitter_handles_html_table_block():
    """Test that TextSplitter can split HTML blocks containing tables."""
    tokenizer = CharacterTokenizer()
    splitter = BlockSplitter(
        tokenizer,
        options=SplitOptions(block_options={"html_table": TableBlockParams()}),
    )

    from lumberjack.core.models import DocumentBlock

    # Create an HTML table block
    html_table_block = DocumentBlock(
        kind="html_table",
        text="<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
        start_line=1,
        end_line=1,
    )

    # Test that the block can be split
    pieces = splitter.split_oversized_block(
        html_table_block,
        default_budget=1000,
    )

    assert pieces is not None
    assert len(pieces) > 0


def test_table_splitter_reads_table_params_from_options() -> None:
    tokenizer = CharacterTokenizer()
    splitter = BlockSplitter(
        tokenizer,
        options=SplitOptions(
            block_options={
                "table": TableBlockParams(max_tokens=28, repeat_header=False)
            },
        ),
    )

    from lumberjack.core.models import DocumentBlock

    block = DocumentBlock(
        kind="table",
        text=(
            "| Name | Value |\n"
            "| ---- | ----- |\n"
            "| Alpha | 100 |\n"
            "| Beta | 200 |\n"
            "| Gamma | 300 |"
        ),
    )
    pieces = splitter.split_table_block(block)

    assert len(pieces) == 3
    assert "| Name | Value |" in pieces[0][0]
    assert all("| Name | Value |" not in piece[0] for piece in pieces[1:])


def test_markdown_parser_with_html_table():
    """Test that the markdown parser correctly handles HTML tables in markdown."""
    parser = MarkdownParser()

    markdown = """# Document with HTML Table

<table>
  <tr><th>Name</th><th>Value</th></tr>
  <tr><td>A</td><td>1</td></tr>
  <tr><td>B</td><td>2</td></tr>
</table>

Some text after the table.
"""

    document = parser.parse(markdown)

    # Find html_table blocks (HTML tables should be identified as html_table type)
    html_table_blocks = []

    def find_html_table_blocks(section):
        for block in section.blocks:
            if block.kind == "html_table":
                html_table_blocks.append(block)
        for child in section.children:
            find_html_table_blocks(child)

    find_html_table_blocks(document.root)

    assert len(html_table_blocks) > 0
    assert "table" in html_table_blocks[0].text.lower()


def test_splitter_with_html_table_in_document():
    """Test splitting a document containing HTML tables."""
    parser = MarkdownParser()
    splitter = create_splitter("sibling")

    markdown = """# Document with HTML Table

<table>
  <tr><th>Name</th><th>Value</th></tr>
  <tr><td>A</td><td>1</td></tr>
  <tr><td>B</td><td>2</td></tr>
  <tr><td>C</td><td>3</td></tr>
  <tr><td>D</td><td>4</td></tr>
</table>

Some text after the table.
"""

    document = parser.parse(markdown)
    chunks = splitter.split(document)

    assert len(chunks) > 0

    # Find chunks that contain table content
    table_chunks = [c for c in chunks if "table" in c.body.lower() or "|" in c.body]
    assert len(table_chunks) > 0


def test_html_table_parser_handles_multiple_tables():
    """Test parsing HTML content with multiple tables."""
    parser = HTMLTableParser()
    html = """<table><tr><th>A</th></tr><tr><td>1</td></tr></table>
<p>Text between tables</p>
<table><tr><th>B</th></tr><tr><td>2</td></tr></table>"""

    tables = parser.extract_tables(html)
    assert len(tables) == 2


def test_html_table_parser_handles_empty_table():
    """Test parsing an empty HTML table."""
    parser = HTMLTableParser()
    html = "<table></table>"

    tables = parser.extract_tables(html)
    assert len(tables) == 1
    assert len(tables[0].headers) == 0
    assert len(tables[0].rows) == 0


def test_html_table_parser_handles_nested_html_in_cells():
    """Test parsing table cells with nested HTML content."""
    parser = HTMLTableParser()
    html = "<table><tr><td><strong>Bold</strong> text</td><td><em>Italic</em></td></tr></table>"

    tables = parser.extract_tables(html)
    assert len(tables) == 1

    table = tables[0]
    assert len(table.rows) == 1

    # Check that nested HTML is stripped
    cell = table.rows[0].cells[0]
    assert cell.text == "Bold text"
    assert "<strong>" not in cell.text

    cell2 = table.rows[0].cells[1]
    assert cell2.text == "Italic"


def test_html_table_parser_handles_br_tags():
    """Test that <br> tags are converted to newlines in table cells."""
    parser = HTMLTableParser()
    html = "<table><tr><td>Line 1<br>Line 2</td></tr></table>"

    tables = parser.extract_tables(html)
    assert len(tables) == 1

    cell = tables[0].rows[0].cells[0]
    assert "\n" in cell.text
    assert "Line 1" in cell.text
    assert "Line 2" in cell.text


def test_html_table_with_complex_attributes():
    """Test parsing table with various HTML attributes."""
    parser = HTMLTableParser()
    html = """<table border="1" cellpadding="5">
        <tr style="background: #fff">
            <th class="header" colspan="2">Header</th>
        </tr>
        <tr>
            <td rowspan="2">Cell 1</td>
            <td>Cell 2</td>
        </tr>
    </table>"""

    tables = parser.extract_tables(html)
    assert len(tables) == 1

    table = tables[0]
    header_row = table.headers[0]
    assert header_row.cells[0].col_span == 2

    data_row = table.rows[0]
    assert data_row.cells[0].row_span == 2
