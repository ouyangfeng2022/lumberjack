from __future__ import annotations

from pathlib import Path

import pytest
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

from lumberjack.core.parsers.markdown.parser import (
    MarkdownBlockSpec,
    MarkdownItParser,
    MarkdownParser,
)

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "markdown" / "sample.md"
).read_text(encoding="utf-8")

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


def test_parser_captures_commonmark_blocks_and_inlines() -> None:
    document = MarkdownParser().parse(
        COMMONMARK_FIXTURE, document_title="commonmark.md"
    )
    heading = document.root.children[0]

    assert heading.title == "Heading with [link](https://example.com)"
    assert [inline.kind for inline in heading.title_inlines] == ["text", "link"]

    kinds = [block.kind for block in heading.blocks]
    assert kinds == [
        "paragraph",
        "blockquote",
        "list",
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

    fenced = heading.blocks[3]
    assert fenced.attrs["language"] == "python"
    assert fenced.attrs["literal"] == 'print("fenced")'

    indented = heading.blocks[4]
    assert indented.kind == "code_block"
    assert indented.attrs["literal"] == 'print("indented")'
    assert document.reference_definitions == {
        "item-ref": {"destination": "/target", "title": "Reference Title"}
    }


def test_markdown_it_parser_supports_setext_tables_and_extended_inlines() -> None:
    document = MarkdownParser().parse(
        MARKDOWN_IT_FIXTURE, document_title="markdown-it.md"
    )
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
    assert document.reference_definitions == {
        "ref": {"destination": "/target", "title": "Title"}
    }


def test_markdown_it_parser_can_disable_setext_headings() -> None:
    document = MarkdownItParser(disable_lheading=True).parse(
        "Title\n=====\n\nbody",
        document_title="setext.md",
    )

    assert document.root.children == []
    assert [block.kind for block in document.root.blocks] == ["paragraph", "paragraph"]
    assert document.root.blocks[0].text == "Title\n====="


def test_markdown_it_parser_handles_all_block_and_inline_tokens_in_comprehensive_fixture() -> (
    None
):
    parser = MarkdownItParser()
    env: dict[str, object] = {}
    tokens = parser._parser.parse(COMPREHENSIVE_FIXTURE, env)

    block_types = {token.type for token in tokens}
    inline_types = {
        child.type
        for token in tokens
        if token.type == "inline"
        for child in (token.children or [])
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
    parser._parser.parse = lambda _text, _env: [  # ty: ignore[invalid-assignment]
        Token("mystery_block", "", 0, map=[0, 1], content="@@ mystery @@")
    ]

    document = parser.parse("@@ mystery @@", document_title="mystery.md")

    assert len(document.root.blocks) == 1
    assert document.root.blocks[0].kind == "mystery_block"
    assert document.root.blocks[0].text == "@@ mystery @@"
    assert document.root.blocks[0].attrs["source_token_type"] == "mystery_block"


def test_markdown_block_spec_maps_custom_token_to_declared_kind() -> None:
    parser = MarkdownItParser(
        block_specs=(
            MarkdownBlockSpec(
                kind="Callout",
                token_types=("callout_open",),
            ),
        )
    )
    parser._parser.parse = lambda _text, _env: [  # ty: ignore[invalid-assignment]
        Token("callout_open", "div", 1, map=[0, 1]),
        Token("callout_close", "div", -1),
    ]

    document = parser.parse("!!! note", document_title="callout.md")

    assert "callout" in parser.block_kinds
    assert document.root.blocks[0].kind == "callout"
    assert document.root.blocks[0].text == "!!! note"
    assert document.root.blocks[0].attrs["source_token_type"] == "callout_open"


def test_markdown_parser_extra_block_kinds_are_declared_without_token_mapping() -> None:
    parser = MarkdownItParser(extra_block_kinds=("Custom_Block", " aside "))

    assert "custom_block" in parser.block_kinds
    assert "aside" in parser.block_kinds


def test_markdown_parser_rejects_string_extra_block_kinds() -> None:
    with pytest.raises(
        TypeError, match="extra_block_kinds must be an iterable of strings"
    ):
        MarkdownItParser(extra_block_kinds="aside")  # ty: ignore[invalid-argument-type]


def test_markdown_parser_rejects_non_string_extra_block_kind() -> None:
    with pytest.raises(TypeError, match="block kind must be a string"):
        MarkdownItParser(extra_block_kinds=(object(),))  # ty: ignore[invalid-argument-type]


def test_markdown_block_spec_rejects_empty_kind() -> None:
    with pytest.raises(ValueError, match="block kind cannot be empty"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind=" ",
                    token_types=("callout_open",),
                ),
            )
        )


def test_markdown_block_spec_rejects_empty_token_type() -> None:
    with pytest.raises(ValueError, match="token type cannot be empty"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind="callout",
                    token_types=(" ",),
                ),
            )
        )


def test_markdown_block_spec_rejects_conflicting_token_kind_mapping() -> None:
    with pytest.raises(ValueError, match="conflicting block spec"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind="callout",
                    token_types=("custom_open",),
                ),
                MarkdownBlockSpec(
                    kind="aside",
                    token_types=("custom_open",),
                ),
            )
        )


def test_markdown_block_spec_rejects_builtin_token_type() -> None:
    with pytest.raises(ValueError, match="handled internally"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind="custom_paragraph",
                    token_types=("paragraph_open",),
                ),
            )
        )


def test_markdown_block_spec_rejects_string_token_types() -> None:
    with pytest.raises(TypeError, match="token_types must be an iterable of strings"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind="callout",
                    token_types="callout_open",  # ty: ignore[invalid-argument-type]
                ),
            )
        )


def test_markdown_block_spec_rejects_non_string_token_type() -> None:
    with pytest.raises(TypeError, match="token type must be a string"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind="callout",
                    token_types=(object(),),  # ty: ignore[invalid-argument-type]
                ),
            )
        )


def test_markdown_block_spec_rejects_non_callable_handler() -> None:
    with pytest.raises(TypeError, match="block spec handler must be callable"):
        MarkdownItParser(
            block_specs=(
                MarkdownBlockSpec(
                    kind="callout",
                    token_types=("callout_open",),
                    handler=object(),  # ty: ignore[invalid-argument-type]
                ),
            )
        )


def test_markdown_block_spec_maps_leaf_token_to_declared_kind() -> None:
    parser = MarkdownItParser(
        block_specs=(
            MarkdownBlockSpec(
                kind="directive",
                token_types=("directive",),
            ),
        )
    )
    parser._parser.parse = lambda _text, _env: [  # ty: ignore[invalid-assignment]
        Token("directive", "", 0, map=[0, 1], content=":: directive")
    ]

    document = parser.parse(":: directive", document_title="directive.md")

    assert "directive" in parser.block_kinds
    assert document.root.blocks[0].kind == "directive"
    assert document.root.blocks[0].text == ":: directive"
    assert document.root.blocks[0].attrs["source_token_type"] == "directive"


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

    assert [block.kind for block in document.root.blocks] == [
        "paragraph",
        "footnote_block",
    ]
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
    document = MarkdownParser().parse(
        NORMALIZED_SOURCE_FIXTURE, document_title="normalized.md"
    )
    heading = document.root.children[0]

    fenced, indented = heading.blocks

    assert fenced.kind == "code_fence"
    assert fenced.start_line == 5
    assert fenced.end_line == 7

    assert indented.kind == "code_block"
    assert indented.start_line == 9
    assert indented.end_line == 9


def test_parser_normalizes_only_surrounding_newlines_on_block_text() -> None:
    document = MarkdownParser().parse(
        "# A\n\n    print('indented')\n",
        document_title="indented.md",
    )

    block = document.root.children[0].blocks[0]

    assert block.kind == "code_block"
    assert block.text == "    print('indented')"


def test_user_provided_title_takes_priority_over_front_matter() -> None:
    """User-provided document_title takes priority over front matter title."""
    md = "---\ntitle: FM Title\n---\n\n# Heading\n\nBody."
    document = MarkdownParser().parse(md, document_title="external.md")

    assert document.title == "external.md"
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

    assert document.title == "fallback.md"
    assert document.metadata["path"] == "/tmp/guide.md"
    assert document.metadata["author"] == "Override"
    assert document.metadata["title"] == "Guide"


def test_no_document_title_uses_front_matter_title() -> None:
    """Without explicit document_title, front matter title is used."""
    md = "---\ntitle: From Front Matter\n---\n\n# Heading\n\nBody."
    document = MarkdownParser().parse(md)

    assert document.title == "From Front Matter"
    assert document.metadata["title"] == "From Front Matter"


def test_no_document_title_no_front_matter_uses_first_h1() -> None:
    """Without document_title and front matter, first H1 heading is used."""
    md = "# My Document\n\nSome content.\n\n## Section\n\nMore."
    document = MarkdownParser().parse(md)

    assert document.title == "My Document"


def test_no_document_title_no_front_matter_h2_only_uses_anonymous() -> None:
    """Without document_title, front matter, or H1 heading, falls back to Anonymous."""
    md = "## Section\n\nContent without H1."
    document = MarkdownParser().parse(md)

    assert document.title == "Anonymous"


def test_no_document_title_no_headings_uses_anonymous() -> None:
    """Without document_title, front matter, or any headings, falls back to Anonymous."""
    md = "Just plain text.\n\nNo headings at all."
    document = MarkdownParser().parse(md)

    assert document.title == "Anonymous"


def test_no_document_title_front_matter_empty_title_uses_first_h1() -> None:
    """Empty front matter title is skipped, falling back to first H1."""
    md = '---\ntitle: ""\n---\n\n# Real Title\n\nContent.'
    document = MarkdownParser().parse(md)

    assert document.title == "Real Title"


def test_thematic_break_is_ignored_by_parser() -> None:
    """thematic_break is treated as a separator and omitted from the AST."""
    md = "Paragraph.\n\n---\n\nMore text."
    document = MarkdownParser().parse(md, document_title="hr.md")
    blocks = document.root.blocks

    assert len(blocks) == 2
    assert blocks[0].kind == "paragraph"
    assert blocks[0].text == "Paragraph."
    assert blocks[1].kind == "paragraph"
    assert blocks[1].text == "More text."


def test_thematic_break_at_start_is_ignored_by_parser() -> None:
    """thematic_break with no preceding block is omitted."""
    md = "---\n\nParagraph."
    document = MarkdownParser().parse(md, document_title="hr-first.md")
    blocks = document.root.blocks

    assert len(blocks) == 1
    assert blocks[0].kind == "paragraph"
    assert blocks[0].text == "Paragraph."


def test_multiple_thematic_breaks_are_ignored_by_parser() -> None:
    """Multiple thematic_break tokens are omitted from the AST."""
    md = "Para 1\n\n---\n\nPara 2\n\n***\n\nPara 3"
    document = MarkdownParser().parse(md, document_title="multi-hr.md")
    blocks = document.root.blocks

    assert len(blocks) == 3
    assert blocks[0].kind == "paragraph"
    assert blocks[0].text == "Para 1"
    assert blocks[1].kind == "paragraph"
    assert blocks[1].text == "Para 2"
    assert blocks[2].kind == "paragraph"
    assert blocks[2].text == "Para 3"


def test_default_block_kinds_match_default_markdown_parser() -> None:
    """Markdown default_block_kinds must match a fresh default parser."""
    parser = MarkdownItParser()

    assert MarkdownItParser.default_block_kinds == parser.block_kinds
    assert "paragraph" in MarkdownItParser.default_block_kinds
    assert "code_fence" in MarkdownItParser.default_block_kinds
    assert "table" in MarkdownItParser.default_block_kinds
    assert "html_table" in MarkdownItParser.default_block_kinds
    assert not hasattr(MarkdownItParser, "default_registry")


def test_block_kinds_reflect_parser_configuration() -> None:
    """block_kinds is auto-detected from the parser's active block rules."""
    parser = MarkdownItParser()
    kinds = parser.block_kinds
    assert "paragraph" in kinds
    assert "code_fence" in kinds
    assert "table" in kinds
    assert "math_block" in kinds
    assert "front_matter" in kinds
    # heading/lheading rules produce SectionNodes, not block kinds
    assert "heading" not in kinds
    assert "lheading" not in kinds
    # hr is skipped
    assert "hr" not in kinds
