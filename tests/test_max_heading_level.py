"""Tests for max_heading_level parameter."""

from lumberjack import lumber
from lumberjack.core.markdown.parser import MarkdownItParser


def test_max_heading_level_limits_section_depth():
    """Test that max_heading_level correctly limits heading parsing."""
    markdown = """
# H1 Section

## H2 Section

### H3 Section

#### H4 Section

##### H5 Section

###### H6 Section

Content in H6 section.
"""

    # Without max_heading_level, all headings are parsed
    doc = MarkdownItParser().parse(markdown)
    assert len(doc.root.children) == 1  # H1
    h1_section = doc.root.children[0]
    assert len(h1_section.children) == 1  # H2
    h2_section = h1_section.children[0]
    assert len(h2_section.children) == 1  # H3
    h3_section = h2_section.children[0]
    assert len(h3_section.children) == 1  # H4
    h4_section = h3_section.children[0]
    assert len(h4_section.children) == 1  # H5
    h5_section = h4_section.children[0]
    assert len(h5_section.children) == 1  # H6
    assert h5_section.children[0].level == 6
    assert len(h5_section.children[0].blocks) == 1  # Content in H6

    # With max_heading_level=3, H4-H6 should be treated as paragraphs
    doc = MarkdownItParser().parse(markdown, max_heading_level=3)
    assert len(doc.root.children) == 1  # H1
    h1_section = doc.root.children[0]
    assert len(h1_section.children) == 1  # H2
    h2_section = h1_section.children[0]
    assert len(h2_section.children) == 1  # H3
    h3_section = h2_section.children[0]
    assert h3_section.level == 3

    # H4, H5, H6 should be blocks, not sections
    assert len(h3_section.blocks) == 4  # H4, H5, H6, and content paragraphs
    block_kinds = [block.kind for block in h3_section.blocks]
    assert block_kinds.count("paragraph") == 4  # All treated as paragraphs

    # Check that H4-H6 text is preserved
    texts = [block.text for block in h3_section.blocks]
    assert any("H4 Section" in text for text in texts)
    assert any("H5 Section" in text for text in texts)
    assert any("H6 Section" in text for text in texts)


def test_max_heading_level_with_lumber():
    """Test that max_heading_level works through the lumber API."""
    markdown = """
# Main Section

## Subsection

### Detail

#### More Detail

Content here.
"""

    # Default behavior - all headings create sections
    chunks = lumber(markdown, splitter="recursive")
    assert len(chunks) >= 1  # At least one chunk

    # Check that all heading levels are present in the chunk
    chunk = chunks[0]
    assert len(chunk.headings) == 4  # H1, H2, H3, H4

    # With max_heading_level=2, only H1 and H2 create sections
    chunks = lumber(markdown, splitter="recursive", max_heading_level=2)
    chunk = chunks[0]
    # Should only have H1 and H2 in headings
    assert len(chunk.headings) == 2  # Only H1 and H2
    assert chunk.headings[0][0] == 1  # H1
    assert chunk.headings[1][0] == 2  # H2

    # Check that H3 and H4 are in the body as text
    assert "### Detail" in chunk.body
    assert "#### More Detail" in chunk.body


def test_max_heading_level_instance_vs_parse_parameter():
    """Test that parse parameter overrides instance setting."""
    markdown = """
# H1

## H2

### H3
"""

    # Instance setting
    parser = MarkdownItParser(max_heading_level=2)
    doc = parser.parse(markdown)
    h1 = doc.root.children[0]
    assert len(h1.children) == 1  # H2
    assert len(h1.children[0].blocks) == 1  # H3 as paragraph

    # Parse parameter overrides instance setting
    doc = parser.parse(markdown, max_heading_level=1)
    h1 = doc.root.children[0]
    assert len(h1.children) == 0  # No H2 section
    assert len(h1.blocks) == 2  # H2 and H3 as paragraphs


def test_max_heading_level_none_means_all():
    """Test that None means all headings are parsed."""
    markdown = """
# H1

###### H6
"""

    doc = MarkdownItParser().parse(markdown, max_heading_level=None)
    assert len(doc.root.children) == 1  # H1
    h1 = doc.root.children[0]
    assert len(h1.children) == 1  # H6 (nested under H1)


def test_max_heading_level_zero_disables_all_headings():
    """Test that max_heading_level=0 treats all headings as paragraphs."""
    markdown = """
# H1

## H2

### H3
"""

    doc = MarkdownItParser().parse(markdown, max_heading_level=0)
    assert len(doc.root.children) == 0  # No sections
    assert len(doc.root.blocks) == 3  # All three headings as paragraphs


if __name__ == "__main__":
    test_max_heading_level_limits_section_depth()
    test_max_heading_level_with_lumber()
    test_max_heading_level_instance_vs_parse_parameter()
    test_max_heading_level_none_means_all()
    test_max_heading_level_zero_disables_all_headings()
    print("All tests passed!")
