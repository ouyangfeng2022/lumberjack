"""Tests for sawyer ``max_heading_level`` constructor arguments."""

import pytest

from lumberjack.feller.markdown.feller import MarkdownItFeller
from tests.helpers import create_sawyer, saw, sawyer_options


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

    doc = MarkdownItFeller().fell(markdown)
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


def _split(markdown: str, *, max_heading_level: int | None):
    document = MarkdownItFeller().fell(markdown)
    sawyer = create_sawyer(
        "sibling",
        **sawyer_options(
            max_tokens=1200,
            max_heading_level=max_heading_level,
        ),
    )
    return saw(sawyer, document)


def test_max_heading_level_on_splitter():
    """Heading-depth limiting is configured directly on a sawyer."""
    markdown = """
# Main Section

## Subsection

### Detail

#### More Detail

Content here.
"""

    # Default behavior - all headings create sections
    chunks = _split(markdown, max_heading_level=None)
    assert len(chunks) >= 1  # At least one chunk

    # A collapsed subtree owns its structural H1 root; deeper headings remain body.
    chunk = chunks[0]
    assert chunk.ancestor_headings == ()
    assert chunk.own_heading == (1, "Main Section")
    assert chunk.section_level == 4

    # With max_heading_level=2, only H1 and H2 remain chunk section context.
    chunks = _split(markdown, max_heading_level=2)
    chunk = chunks[0]
    assert chunk.ancestor_headings == ()
    assert chunk.own_heading == (1, "Main Section")
    assert chunk.section_level == 2

    # Check that H3 and H4 are in the body as text
    assert "### Detail" in chunk.body
    assert "#### More Detail" in chunk.body


@pytest.mark.parametrize(
    "splitter_name",
    ("sibling", "incremental-sibling", "subtree", "section"),
)
def test_max_heading_level_manual_splitter_pipeline(splitter_name: str):
    """Manual parse -> split users configure heading depth on the sawyer."""
    markdown = """
# H1

## H2

### H3
"""

    doc = MarkdownItFeller().fell(markdown)
    h1 = doc.root.children[0]
    assert len(h1.children) == 1  # H2
    assert len(h1.children[0].children) == 1  # H3 remains in parsed AST

    sawyer = create_sawyer(
        splitter_name,
        **sawyer_options(max_tokens=500, max_heading_level=2),
    )
    chunks = saw(sawyer, doc)

    assert len(chunks) == 1
    chunk = chunks[0]
    if splitter_name == "section":
        assert chunk.ancestor_headings == ((1, "H1"),)
        assert chunk.own_heading == (2, "H2")
    else:
        assert chunk.ancestor_headings == ()
        assert chunk.own_heading == (1, "H1")
    assert chunk.section_level == 2
    assert "### H3" in chunk.body


def test_max_heading_level_none_means_all():
    """None means all parsed headings remain section context."""
    markdown = """
# H1

###### H6

Body.
"""

    chunks = _split(markdown, max_heading_level=None)
    chunk = chunks[0]
    assert chunk.ancestor_headings == ()
    assert chunk.own_heading == (1, "H1")
    assert chunk.section_level == 6


def test_max_heading_level_zero_disables_all_headings():
    """A zero max heading level treats every heading as body text."""
    markdown = """
# H1

## H2

### H3
"""

    chunks = _split(markdown, max_heading_level=0)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.ancestor_headings == ()
    assert chunk.section_level == 0
    assert chunk.body == "# H1\n\n## H2\n\n### H3"


if __name__ == "__main__":
    test_parser_preserves_full_heading_depth()
    test_max_heading_level_on_splitter()
    for _splitter_name in (
        "sibling",
        "incremental-sibling",
        "subtree",
        "section",
    ):
        test_max_heading_level_manual_splitter_pipeline(_splitter_name)
    test_max_heading_level_none_means_all()
    test_max_heading_level_zero_disables_all_headings()
    print("All tests passed!")
