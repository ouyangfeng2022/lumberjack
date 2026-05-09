from __future__ import annotations

from pathlib import Path

from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

from lumberjack.core.parser import MarkdownItParser, MarkdownParser, create_parser

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

MARKDOWN_IT_FIXTURE = """Title
=====

| A | B |
| - | - |
| 1 | 2 |

~~gone~~ and github.com and <https://example.com>

[ref]: /target "Title"
"""

COMPREHENSIVE_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "markdown" / "commonmark-spec.md"
).read_text(encoding="utf-8")


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


def test_create_parser_routes_default_and_fallback_names() -> None:
    assert isinstance(create_parser("default"), MarkdownItParser)
    assert isinstance(create_parser("markdown-it"), MarkdownItParser)


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
    assert document.reference_definitions == {
        "item-ref": {"destination": "/target", "title": "Reference Title"}
    }


def test_markdown_it_parser_supports_setext_tables_and_extended_inlines() -> None:
    document = MarkdownParser().parse(MARKDOWN_IT_FIXTURE, document_title="markdown-it.md")
    heading = document.root.children[0]

    assert heading.title == "Title"
    assert heading.start_line == 1
    assert [block.kind for block in heading.blocks] == ["table", "paragraph"]

    table = heading.blocks[0]
    assert table.start_line == 4
    assert table.end_line == 6
    assert table.text == "| A | B |\n| - | - |\n| 1 | 2 |"

    paragraph = heading.blocks[1]
    assert [inline.kind for inline in paragraph.inlines] == [
        "strikethrough",
        "text",
        "autolink",
        "text",
        "autolink",
    ]
    assert paragraph.inlines[0].children[0].text == "gone"
    assert paragraph.inlines[2].attrs["destination"] == "http://github.com"
    assert paragraph.inlines[2].attrs["syntax"] == "linkify"
    assert paragraph.inlines[4].attrs["destination"] == "https://example.com"
    assert paragraph.inlines[4].attrs["syntax"] == "autolink"
    assert all(block.kind != "link_reference_definition" for block in heading.blocks)
    assert document.reference_definitions == {"ref": {"destination": "/target", "title": "Title"}}


def test_markdown_it_parser_handles_all_block_and_inline_tokens_in_comprehensive_fixture() -> None:
    parser = MarkdownItParser()
    env: dict[str, object] = {}
    tokens = parser._parser.parse(COMPREHENSIVE_FIXTURE, env)

    block_types = {token.type for token in tokens}
    inline_types = {
        child.type for token in tokens if token.type == "inline" for child in (token.children or [])
    }

    assert block_types == {
        "blockquote_close",
        "blockquote_open",
        "bullet_list_close",
        "bullet_list_open",
        "code_block",
        "fence",
        "heading_close",
        "heading_open",
        "hr",
        "html_block",
        "inline",
        "list_item_close",
        "list_item_open",
        "math_block",
        "ordered_list_close",
        "ordered_list_open",
        "paragraph_close",
        "paragraph_open",
        "table_close",
        "table_open",
        "tbody_close",
        "tbody_open",
        "td_close",
        "td_open",
        "th_close",
        "th_open",
        "thead_close",
        "thead_open",
        "tr_close",
        "tr_open",
    }
    assert inline_types == {
        "code_inline",
        "em_close",
        "em_open",
        "hardbreak",
        "html_inline",
        "image",
        "link_close",
        "link_open",
        "math_inline",
        "s_close",
        "s_open",
        "softbreak",
        "strong_close",
        "strong_open",
        "text",
    }


def test_markdown_it_parser_preserves_unknown_block_tokens_as_raw_markdown() -> None:
    parser = MarkdownItParser()
    parser._parser.parse = lambda _text, _env: [
        Token("mystery_block", "", 0, map=[0, 1], content="@@ mystery @@")
    ]

    document = parser.parse("@@ mystery @@", document_title="mystery.md")

    assert len(document.root.blocks) == 1
    assert document.root.blocks[0].kind == "mystery_block"
    assert document.root.blocks[0].text == "@@ mystery @@"
    assert document.root.blocks[0].attrs["source_token_type"] == "mystery_block"


def test_markdown_it_parser_supports_task_list_plugin() -> None:
    parser = MarkdownItParser(plugins=(tasklists_plugin,))
    markdown = "- [x] done\n- [ ] todo"

    document = parser.parse(markdown, document_title="tasks.md")

    assert len(document.root.blocks) == 1
    task_list = document.root.blocks[0]
    assert task_list.kind == "list"
    assert task_list.text == markdown
    assert task_list.children[0].text == "- [x] done"
    assert task_list.children[1].text == "- [ ] todo"
    assert task_list.children[0].children[0].inlines[0].kind == "inline_html"


def test_markdown_it_parser_supports_footnote_plugin() -> None:
    parser = MarkdownItParser(plugins=(footnote_plugin,))
    markdown = "Footnote ref[^1].\n\n[^1]: Footnote body\n    continued"

    document = parser.parse(markdown, document_title="footnotes.md")

    assert [block.kind for block in document.root.blocks] == ["paragraph", "footnote_block"]
    assert document.root.blocks[0].text == "Footnote ref[^1]."
    assert [inline.kind for inline in document.root.blocks[0].inlines] == [
        "text",
        "footnote_ref",
        "text",
    ]
    assert document.root.blocks[0].inlines[1].text == "[^1]"
    assert document.root.blocks[1].text == "[^1]: Footnote body\n    continued"
    assert document.root.blocks[1].children[0].kind == "footnote"


def test_parser_distinguishes_tight_and_loose_lists() -> None:
    tight_md = "- a\n- b\n- c"
    loose_md = "- a\n\n- b\n\n- c"

    tight_doc = MarkdownParser().parse(tight_md, document_title="tight.md")
    loose_doc = MarkdownParser().parse(loose_md, document_title="loose.md")

    tight_list = tight_doc.root.blocks[0]
    loose_list = loose_doc.root.blocks[0]

    assert tight_list.kind == "list"
    assert tight_list.attrs["tight"] is True

    assert loose_list.kind == "list"
    assert loose_list.attrs["tight"] is False


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


def test_front_matter_title_overrides_external_document_title() -> None:
    """Front matter title takes priority over externally provided document_title."""
    md = "---\ntitle: FM Title\n---\n\n# Heading\n\nBody."
    document = MarkdownParser().parse(md, document_title="external.md")

    assert document.title == "FM Title"
    assert document.metadata["title"] == "FM Title"


def test_front_matter_without_title_falls_back_to_external() -> None:
    """Front matter without a title field uses the external document_title."""
    md = "---\nauthor: Alice\n---\n\nBody."
    document = MarkdownParser().parse(md, document_title="external.md")

    assert document.title == "external.md"
    assert document.metadata["author"] == "Alice"


def test_front_matter_populates_metadata() -> None:
    """YAML front matter key-value pairs populate document.metadata."""
    md = "---\ntitle: Guide\nauthor: Bob\nversion: 2\ntags:\n  - python\n  - markdown\n---\n\nBody."
    document = MarkdownParser().parse(md, document_title="fallback.md")

    assert document.metadata == {
        "title": "Guide",
        "author": "Bob",
        "version": 2,
        "tags": ["python", "markdown"],
    }


def test_no_front_matter_uses_external_values() -> None:
    """Without front matter, external document_title and document_metadata are used."""
    md = "# Hello\n\nWorld."
    document = MarkdownParser().parse(
        md,
        document_title="hello.md",
        document_metadata={"path": "/tmp/hello.md"},
    )

    assert document.title == "hello.md"
    assert document.metadata == {"path": "/tmp/hello.md"}


def test_malformed_front_matter_falls_back_gracefully() -> None:
    """Malformed YAML front matter does not crash; external values are preserved."""
    md = "---\n: invalid: yaml: [\n---\n\nBody."
    document = MarkdownParser().parse(md, document_title="fallback.md")

    assert document.title == "fallback.md"
    assert document.metadata == {}


def test_front_matter_title_empty_string_uses_external() -> None:
    """An empty front matter title is treated as absent."""
    md = '---\ntitle: ""\n---\n\nBody.'
    document = MarkdownParser().parse(md, document_title="external.md")

    assert document.title == "external.md"


def test_front_matter_and_external_metadata_merge() -> None:
    """Front matter metadata and external metadata merge, with external values winning."""
    md = "---\ntitle: Guide\nauthor: Bob\n---\n\nBody."
    document = MarkdownParser().parse(
        md,
        document_title="fallback.md",
        document_metadata={"path": "/tmp/guide.md", "author": "Override"},
    )

    assert document.title == "Guide"
    assert document.metadata["path"] == "/tmp/guide.md"
    assert document.metadata["author"] == "Override"
    assert document.metadata["title"] == "Guide"
