"""Runnable splitter entry: split one file and inspect the resulting chunks.

Usage::

    python -m lumberjack.splitter FILE [--splitter NAME] [--max-tokens N] ...

Reads ``-`` as UTF-8 text from stdin. Runs the built-in parse-split-finalize
pipeline and prints the same chunk-result JSON envelope as the ``lumber`` CLI,
so the two outputs can be diffed directly. Batching, output files, and trace
stages stay in ``lumber``; this entry focuses on interactive split inspection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from .._internal.formats import SUPPORTED_FORMATS
from .._internal.pipeline import BUILTIN_SPLITTER_NAMES, split_source
from ..models import InputFormat
from ..serialization import split_result_to_dict


def build_parser() -> argparse.ArgumentParser:
    """Build the ``python -m lumberjack.splitter`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m lumberjack.splitter",
        description="Split one document and print the chunk result as JSON",
    )
    parser.add_argument("input", help="Document file path, or - to read stdin text")
    parser.add_argument(
        "--format",
        choices=sorted(SUPPORTED_FORMATS),
        default="auto",
        metavar="FORMAT",
        help="Input format (default: auto-detect from extension and content)",
    )
    split_options = parser.add_argument_group("splitting")
    split_options.add_argument(
        "--splitter",
        choices=BUILTIN_SPLITTER_NAMES,
        default="section",
        metavar="NAME",
        help=(
            "Splitter implementation. 'sibling'/'subtree'/'section' default "
            "to incremental counting; 'exact-*' selects full recounting. "
            "Use 'record' for CSV/TSV, JSONL, and log files."
        ),
    )
    split_options.add_argument(
        "--tokenizer",
        choices=("approx", "tiktoken", "transformers"),
        default="approx",
        metavar="ENGINE",
        help="Tokenizer engine used to encode and count text (default: approx)",
    )
    split_options.add_argument(
        "--max-tokens", type=int, default=1200, help="Maximum tokens per chunk"
    )
    split_options.add_argument(
        "--ideal-max-tokens-ratio",
        type=float,
        default=0.8,
        help="Preferred split budget as a ratio of --max-tokens",
    )
    split_options.add_argument(
        "--merge-below-ratio",
        type=float,
        default=0.125,
        help="Tail-fragment merge threshold as a fraction of --max-tokens "
        "in [0.0, 1.0); 0 disables merging (default: 0.125)",
    )
    split_options.add_argument(
        "--heading-sensitive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include the chunk's external heading-path tokens in split budgets "
        "(default: enabled). Headings are always returned as metadata.",
    )
    split_options.add_argument(
        "--max-heading-level",
        type=int,
        default=None,
        help="Maximum heading level to keep as chunk section context. "
        "Deeper headings are rendered as body text.",
    )
    return parser


def _read_source(value: str) -> str | Path:
    if value == "-":
        return sys.stdin.read()
    path = Path(value)
    if not path.is_file():
        raise SystemExit(f"error: no such file: {path}")
    return path


def main() -> None:
    """Entry point: split one document and print the chunk result."""
    args = build_parser().parse_args()
    source = _read_source(args.input)
    result = split_source(
        source,
        format=cast(InputFormat, args.format),
        tokenizer=args.tokenizer,
        splitter=args.splitter,
        max_tokens=args.max_tokens,
        ideal_max_tokens_ratio=args.ideal_max_tokens_ratio,
        merge_below_ratio=args.merge_below_ratio,
        heading_sensitive=args.heading_sensitive,
        max_heading_level=args.max_heading_level,
    )
    print(json.dumps(split_result_to_dict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
