"""Integration tests for HTML table handling with table isolation."""

from __future__ import annotations

from lumberjack import lumber
from lumberjack.core.models import BaseParams, TableBlockParams


def test_html_table_with_table_isolation():
    """Test that HTML tables are recognized when table isolation is set."""
    markdown = """# Document with HTML Table

<table>
  <caption>Sample Data</caption>
  <tr><th>Name</th><th>Value</th></tr>
  <tr><td>Item 1</td><td>100</td></tr>
  <tr><td>Item 2</td><td>200</td></tr>
  <tr><td>Item 3</td><td>300</td></tr>
</table>

Some text after the table.
"""

    # Set html_table isolation
    chunks = lumber(
        markdown,
        max_tokens=500,
        block_options={"html_table": BaseParams(isolated=True)},
    )

    # Should have at least 2 chunks: table chunk and text chunk
    assert len(chunks) >= 2

    # Find the html_table chunk
    table_chunks = [c for c in chunks if c.chunk_type == "html_table"]
    assert len(table_chunks) == 1

    table_chunk = table_chunks[0]
    # Verify it's HTML format (should contain HTML tags)
    assert "<table>" in table_chunk.body
    assert "</table>" in table_chunk.body
    # Should NOT be converted to markdown format
    assert "| Name |" not in table_chunk.body


def test_html_table_preserves_original_format():
    """Test that HTML tables keep their original HTML format."""
    markdown = """# HTML Table Test

<table border="1">
  <tr><th style="color: red">Header</th></tr>
  <tr><td>Data</td></tr>
</table>
"""

    chunks = lumber(markdown, max_tokens=500)

    # Find chunk with table content
    table_chunks = [c for c in chunks if "<table" in c.body and "</table>" in c.body]
    assert len(table_chunks) >= 1

    # Verify original HTML is preserved in at least one chunk
    found = False
    for chunk in table_chunks:
        if 'border="1"' in chunk.body and 'style="color: red"' in chunk.body:
            found = True
            break

    assert found, "HTML table attributes should be preserved"


def test_large_html_table_splitting():
    """Test that large HTML tables are split while preserving HTML format."""
    # Create a large HTML table
    rows = []
    for i in range(20):
        rows.append(
            f"  <tr><td>Item {i}</td><td>Value {i}</td><td>Description {i}</td></tr>"
        )

    markdown = f"""# Large HTML Table

<table>
  <tr><th>ID</th><th>Name</th><th>Description</th></tr>
{chr(10).join(rows)}
</table>
"""

    # Set small token budget to force splitting
    chunks = lumber(markdown, max_tokens=200, merge_below_tokens=-1)

    # Should be split into multiple chunks
    assert len(chunks) > 1

    # All table chunks should preserve HTML format
    table_chunks = [c for c in chunks if "<table" in c.body and "</table>" in c.body]
    for chunk in table_chunks:
        assert "<table" in chunk.body
        assert "</table>" in chunk.body
        assert "<tr>" in chunk.body
        assert "<td>" in chunk.body
        # Should NOT contain markdown table syntax
        assert "|---|" not in chunk.body


def test_large_html_table_can_omit_repeated_header_rows():
    """HTML table params can keep header rows only on the first split piece."""
    rows = [
        f"  <tr><td>Item {i}</td><td>Value {i}</td><td>Description {i}</td></tr>"
        for i in range(20)
    ]
    markdown = f"""# Large HTML Table

<table>
  <tr><th>ID</th><th>Name</th><th>Description</th></tr>
{chr(10).join(rows)}
</table>
"""

    chunks = lumber(
        markdown,
        max_tokens=200,
        merge_below_tokens=-1,
        block_options={"html_table": TableBlockParams(repeat_header=False)},
    )

    table_chunks = [c for c in chunks if "<table" in c.body and "</table>" in c.body]
    assert len(table_chunks) > 1
    assert "<th>ID</th>" in table_chunks[0].body
    assert all("<th>ID</th>" not in chunk.body for chunk in table_chunks[1:])
    assert all("<td>Item" in chunk.body for chunk in table_chunks)


def test_html_table_vs_markdown_table_distinction():
    """Test that HTML tables and markdown tables are handled correctly."""
    markdown = """# Mixed Tables

## HTML Table
<table>
  <tr><th>A</th><th>B</th></tr>
  <tr><td>1</td><td>2</td></tr>
</table>

## Markdown Table
| C | D |
|---|---|
| 3 | 4 |
"""

    chunks = lumber(markdown, max_tokens=500)

    # Both types of tables should be preserved in the chunks
    has_html_table = any("<table" in c.body and "<tr>" in c.body for c in chunks)
    has_markdown_table = any("| C |" in c.body and "|---|" in c.body for c in chunks)

    # Both should be present
    assert has_html_table
    assert has_markdown_table


def test_html_table_with_caption_preserved():
    """Test that HTML table captions are preserved."""
    markdown = """# Table with Caption

<table>
  <caption>This is a caption</caption>
  <tr><th>Column</th></tr>
  <tr><td>Data</td></tr>
</table>
"""

    chunks = lumber(markdown, max_tokens=500)

    # Find table chunk
    table_chunks = [c for c in chunks if "<table" in c.body and "</table>" in c.body]
    assert len(table_chunks) == 1

    chunk = table_chunks[0]
    assert "<caption>This is a caption</caption>" in chunk.body


def test_html_table_attributes_preserved():
    """Test that HTML table attributes like rowspan/colspan are preserved."""
    markdown = """# Complex HTML Table

<table>
  <tr><th colspan="2">Spanning Header</th></tr>
  <tr><td>A</td><td>B</td></tr>
  <tr><td rowspan="2">C</td><td>D</td></tr>
  <tr><td>E</td></tr>
</table>
"""

    chunks = lumber(markdown, max_tokens=500)

    # Find table chunk
    table_chunks = [c for c in chunks if "<table" in c.body and "</table>" in c.body]
    assert len(table_chunks) == 1

    chunk = table_chunks[0]
    assert 'colspan="2"' in chunk.body
    assert 'rowspan="2"' in chunk.body


def test_non_table_html_not_affected():
    """Test that non-table HTML content is not affected."""
    markdown = """# HTML Content

<p>This is a paragraph with <strong>bold text</strong>.</p>

<div>
  <span>Some span content</span>
</div>
"""

    chunks = lumber(markdown, max_tokens=500)

    # Should work normally
    assert len(chunks) > 0
    # Should not contain any table-related content
    for chunk in chunks:
        assert "<table>" not in chunk.body
