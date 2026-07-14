"""Tests for ``SplitOptions.max_heading_level``."""

import pytest

from lumberjack import lumber
from lumberjack.core.models import SplitOptions
from lumberjack.core.parser.markdown.parser import MarkdownItParser
from lumberjack.core.splitter import create_splitter


def test_parser_preserves_full_heading_depth():
    """Parsers keep full structure; heading-depth limiting belongs to splitters."""
    markdown = """
# H1 Section

## H2 Section

### H3 Section

#### H4 Section

##### H5 Section

###### H6 Section

Content in H6 section.
"""

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


def test_max_heading_level_with_lumber():
    """``lumber()`` threads max_heading_level into splitter options."""
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

    # Ancestor metadata excludes the chunk's own H4 title, while section_level
    # still reports the deepest covered heading level.
    chunk = chunks[0]
    assert len(chunk.headings) == 3  # H1, H2, H3 ancestors
    assert chunk.section_level == 4

    # With max_heading_level=2, only H1 and H2 remain chunk section context.
    chunks = lumber(markdown, splitter="recursive", max_heading_level=2)
    chunk = chunks[0]
    # H2 is the chunk's own section title, so only H1 is ancestor metadata.
    assert len(chunk.headings) == 1
    assert chunk.headings[0][0] == 1  # H1
    assert chunk.section_level == 2

    # Check that H3 and H4 are in the body as text
    assert "### Detail" in chunk.body
    assert "#### More Detail" in chunk.body


@pytest.mark.parametrize(
    "splitter_name",
    ("recursive", "incremental-recursive", "subtree", "section"),
)
def test_max_heading_level_manual_splitter_pipeline(splitter_name: str):
    """Manual parse -> split users configure heading depth on SplitOptions."""
    markdown = """
# H1

## H2

### H3
"""

    doc = MarkdownItParser().parse(markdown)
    h1 = doc.root.children[0]
    assert len(h1.children) == 1  # H2
    assert len(h1.children[0].children) == 1  # H3 remains in parsed AST

    splitter = create_splitter(
        splitter_name,
        options=SplitOptions(max_tokens=500, max_heading_level=2),
    )
    chunks = splitter.split(doc)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.headings == ((1, "H1"),)
    assert chunk.section_level == 2
    assert "### H3" in chunk.body


def test_max_heading_level_none_means_all():
    """None means all parsed headings remain section context."""
    markdown = """
# H1

###### H6

Body.
"""

    chunks = lumber(markdown, splitter="recursive", max_heading_level=None)
    chunk = chunks[0]
    assert chunk.headings == ((1, "H1"),)
    assert chunk.section_level == 6


def test_max_heading_level_zero_disables_all_headings():
    """A zero max heading level treats every heading as body text."""
    markdown = """
# H1

## H2

### H3
"""

    chunks = lumber(markdown, splitter="recursive", max_heading_level=0)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.headings == ()
    assert chunk.section_level == 0
    assert chunk.body == "# H1\n\n## H2\n\n### H3"


if __name__ == "__main__":
    test_parser_preserves_full_heading_depth()
    test_max_heading_level_with_lumber()
    for _splitter_name in (
        "recursive",
        "incremental-recursive",
        "subtree",
        "section",
    ):
        test_max_heading_level_manual_splitter_pipeline(_splitter_name)
    test_max_heading_level_none_means_all()
    test_max_heading_level_zero_disables_all_headings()
    print("All tests passed!")
