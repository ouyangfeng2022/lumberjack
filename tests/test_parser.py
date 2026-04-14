from __future__ import annotations

from pathlib import Path

from lumberjack.core.parser import MarkdownParser

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "markdown" / "sample.md").read_text(
    encoding="utf-8"
)

COMMONMARK_FIXTURE = """# Heading with [link](https://example.com)

Paragraph with [inline link](https://example.com "Example"), ![image](image.png "Alt"),
`code`, *emphasis*, **strong**, <https://example.com>, <span>html</span>, and a hard break.
next line.

> Quote
>
> 1. ordered
> 2. list

1. first
2. second

---

```python
print("fenced")
```

    print("indented")

ref [item][item-ref]

[item-ref]: /target "Reference Title"
"""

NORMALIZED_SOURCE_FIXTURE = """# Sample

***

~~~python
print("fenced")
~~~

    print("indented")
"""


def test_parser_builds_heading_tree() -> None:
    """Test that parser builds correct heading tree structure."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    root = document.root

    assert root.title == "sample.md"
    assert len(root.blocks) == 1
    assert len(root.children) == 1
    assert root.children[0].title == "Overview"
    assert root.children[0].children[0].title == "Details"
    assert root.children[0].children[0].children[0].title == "Notes"


def test_parser_ignores_headings_inside_code_fence() -> None:
    """Test that headings inside fenced code blocks are ignored."""
    document = MarkdownParser().parse(FIXTURE, document_title="sample.md")
    details = document.root.children[0].children[0]
    code_blocks = [block for block in details.blocks if block.kind == "code_fence"]

    assert len(code_blocks) == 1
    assert "# This heading-looking line" in code_blocks[0].text
    assert len(details.children) == 1


def test_parser_captures_commonmark_blocks_and_inlines() -> None:
    document = MarkdownParser().parse(COMMONMARK_FIXTURE, document_title="commonmark.md")
    heading = document.root.children[0]

    assert heading.title == "Heading with [link](https://example.com)"
    assert [inline.kind for inline in heading.title_inlines] == ["text", "link"]

    kinds = [block.kind for block in heading.blocks]
    assert kinds == [
        "paragraph",
        "blockquote",
        "list",
        "thematic_break",
        "code_fence",
        "code_block",
        "paragraph",
        "link_reference_definition",
    ]

    paragraph = heading.blocks[0]
    assert [inline.kind for inline in paragraph.inlines] == [
        "text",
        "link",
        "text",
        "image",
        "text",
        "soft_break",
        "code_span",
        "text",
        "emphasis",
        "text",
        "strong",
        "text",
        "autolink",
        "text",
        "inline_html",
        "text",
        "inline_html",
        "text",
        "soft_break",
        "text",
    ]
    assert paragraph.inlines[1].attrs["destination"] == "https://example.com"
    assert paragraph.inlines[3].attrs["destination"] == "image.png"
    assert paragraph.inlines[6].attrs["literal"] == "code"
    assert paragraph.inlines[12].kind == "autolink"

    blockquote = heading.blocks[1]
    assert blockquote.children[1].kind == "list"
    assert blockquote.children[1].children[0].kind == "list_item"

    ordered_list = heading.blocks[2]
    assert ordered_list.attrs["ordered"] is True
    assert ordered_list.children[0].text.startswith("1. ")
    assert ordered_list.children[1].text.startswith("2. ")

    fenced = heading.blocks[4]
    assert fenced.attrs["language"] == "python"
    assert fenced.attrs["literal"] == 'print("fenced")'

    indented = heading.blocks[5]
    assert indented.kind == "code_block"
    assert indented.attrs["literal"] == 'print("indented")'

    reference = heading.blocks[-1]
    assert reference.attrs["label"] == "item-ref"
    assert document.reference_definitions == {
        "item-ref": {"destination": "/target", "title": "Reference Title"}
    }


def test_parser_preserves_line_ranges_for_normalized_block_syntax() -> None:
    document = MarkdownParser().parse(NORMALIZED_SOURCE_FIXTURE, document_title="normalized.md")
    heading = document.root.children[0]

    thematic_break, fenced, indented = heading.blocks

    assert thematic_break.kind == "thematic_break"
    assert thematic_break.start_line == 3
    assert thematic_break.end_line == 3

    assert fenced.kind == "code_fence"
    assert fenced.start_line == 5
    assert fenced.end_line == 7

    assert indented.kind == "code_block"
    assert indented.start_line == 9
    assert indented.end_line == 9
