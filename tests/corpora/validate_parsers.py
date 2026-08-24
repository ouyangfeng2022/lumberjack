from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lumberjack.models import DocTree, DocumentBlock, SectionNode
from lumberjack.parser.docx import DocxParser
from lumberjack.parser.markdown import MarkdownParser

COMMONMARK_0_31_2_SHA256 = (
    "d431b29d97b6f73e69d547109cf5081578fac931e72afe95639ebe766c1b2a20"
)


def walk_sections(section: SectionNode) -> Iterable[SectionNode]:
    yield section
    for child in section.children:
        yield from walk_sections(child)


def walk_blocks(blocks: Iterable[DocumentBlock]) -> Iterable[DocumentBlock]:
    for block in blocks:
        yield block
        yield from walk_blocks(block.children)


def validate_tree(tree: DocTree) -> None:
    if tree.root.level != 0 or tree.root.title != tree.title:
        raise ValueError("invalid root section")
    for section in walk_sections(tree.root):
        for index, child in enumerate(section.children):
            if child.index != index:
                raise ValueError("non-contiguous section indexes")
            if child.level <= section.level:
                raise ValueError("child section level does not increase")
            if child.path != (*section.path, (child.level, child.title)):
                raise ValueError("section path does not match its parent")
        for block in walk_blocks(section.blocks):
            if not block.text:
                raise ValueError("empty block")
            if (block.start_line is None) != (block.end_line is None):
                raise ValueError("partial block source range")
            if (
                block.start_line is not None
                and block.end_line is not None
                and not 1 <= block.start_line <= block.end_line
            ):
                raise ValueError("invalid block source range")


def validate_commonmark(path: Path) -> int:
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != COMMONMARK_0_31_2_SHA256:
        raise ValueError(
            f"unexpected CommonMark corpus SHA-256: {digest}; "
            f"expected {COMMONMARK_0_31_2_SHA256}"
        )
    cases: Any = json.loads(payload)
    if not isinstance(cases, list):
        raise TypeError("CommonMark corpus must be a JSON array")

    parser = MarkdownParser(disable_lheading=False)
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("markdown"), str):
            raise TypeError("invalid CommonMark example")
        tree = parser.parse(
            case["markdown"],
            document_title=f"commonmark-{case.get('example', 'unknown')}.md",
        )
        validate_tree(tree)
    return len(cases)


def validate_docx(paths: Iterable[Path]) -> int:
    parser = DocxParser()
    count = 0
    for path in paths:
        tree = parser.parse(path.read_bytes(), document_title=path.name)
        validate_tree(tree)
        count += 1
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate parser corpora")
    parser.add_argument("--commonmark-json", type=Path)
    parser.add_argument("--docx-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.commonmark_json is None and args.docx_dir is None:
        raise SystemExit("provide --commonmark-json and/or --docx-dir")

    result = {"commonmark": 0, "docx": 0}
    if args.commonmark_json is not None:
        result["commonmark"] = validate_commonmark(args.commonmark_json)
    if args.docx_dir is not None:
        result["docx"] = validate_docx(sorted(args.docx_dir.rglob("*.docx")))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
