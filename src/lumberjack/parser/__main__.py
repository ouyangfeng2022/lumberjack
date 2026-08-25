"""Runnable parser entry: inspect what ``AutoParser`` produces for one file.

Usage::

    python -m lumberjack.parser FILE [--format FORMAT] [--outline]

Reads ``-`` as UTF-8 text from stdin. Prints the complete ``DocTree`` as the
versioned JSON representation by default, or a compact section outline with
``--outline``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import cast

from .._internal.formats import SUPPORTED_FORMATS
from ..models import DocTree, InputFormat, SectionNode
from ..serialization import doc_tree_to_dict
from . import AutoParser


def build_parser() -> argparse.ArgumentParser:
    """Build the ``python -m lumberjack.parser`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m lumberjack.parser",
        description="Parse one document and print its DocTree as JSON",
    )
    parser.add_argument("input", help="Document file path, or - to read stdin text")
    parser.add_argument(
        "--format",
        choices=sorted(SUPPORTED_FORMATS),
        default="auto",
        metavar="FORMAT",
        help="Input format (default: auto-detect from extension and content)",
    )
    parser.add_argument(
        "--outline",
        action="store_true",
        help="Print a compact section-tree outline instead of full JSON",
    )
    return parser


def _read_source(value: str) -> str | Path:
    if value == "-":
        return sys.stdin.read()
    path = Path(value)
    if not path.is_file():
        raise SystemExit(f"error: no such file: {path}")
    return path


def _block_summary(section: SectionNode) -> str:
    counts = Counter(str(block.kind) for block in section.blocks)
    return ", ".join(f"{kind} x{count}" for kind, count in counts.items())


def _section_lines(section: SectionNode, depth: int) -> list[str]:
    label = "root" if section.level <= 0 else f"{'#' * section.level} {section.title}"
    location = f" (line {section.start_line})" if section.start_line is not None else ""
    line = f"{'  ' * depth}{label}{location}: {_block_summary(section) or 'no blocks'}"
    return [
        line,
        *(
            child_line
            for child in section.children
            for child_line in _section_lines(child, depth + 1)
        ),
    ]


def render_outline(tree: DocTree) -> str:
    """Render the section tree as an indented outline with block-kind counts."""
    return "\n".join(
        [
            f"title: {tree.title}",
            f"topology: {tree.topology}",
            *_section_lines(tree.root, 0),
        ]
    )


def main() -> None:
    """Entry point: parse one document and print its DocTree."""
    args = build_parser().parse_args()
    source = _read_source(args.input)
    tree = AutoParser().parse(source, format=cast(InputFormat, args.format))
    if args.outline:
        print(render_outline(tree))
    else:
        print(json.dumps(doc_tree_to_dict(tree), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
