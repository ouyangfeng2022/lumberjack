from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from . import lumber
from .core.block_config import parse_block_config_entry
from .core.markdown.parser import MarkdownItParser

if TYPE_CHECKING:
    from .core.models import BlockConfig


def _parse_block_configs(entries: list[str]) -> dict[str, BlockConfig]:
    """Parse ``KIND[:isolated][:nosplit][:TOKENS]`` strings into a ``{kind: BlockConfig}`` dict.

    Starts from the parser defaults, then applies user overrides.
    """
    registry = MarkdownItParser.default_registry()
    result: dict[str, BlockConfig] = dict(registry.default_handling())
    for entry in entries:
        kind, cfg = parse_block_config_entry(entry, registry)
        result[kind] = cfg
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all split options."""
    parser = argparse.ArgumentParser(description="Markdown / DOCX document splitter")
    parser.add_argument("input", help="Path to a markdown (.md) or DOCX (.docx) file")
    parser.add_argument(
        "--input-format",
        choices=("auto", "markdown", "docx"),
        default="auto",
        help="Input format (default: auto-detect from file extension)",
    )
    parser.add_argument("-o", "--output", help="Optional output file path")
    parser.add_argument(
        "--tokenizer",
        choices=("simple", "tiktoken"),
        default="simple",
        help="Tokenizer implementation",
    )
    parser.add_argument(
        "--splitter",
        choices=("recursive", "section"),
        default="recursive",
        help="Splitter implementation",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=1200, help="Maximum tokens per chunk"
    )
    parser.add_argument(
        "--ideal-max-tokens-ratio",
        type=float,
        default=0.8,
        help="Preferred split budget as a ratio of --max-tokens",
    )
    parser.add_argument(
        "--merge-below-tokens",
        type=int,
        default=50,
        help="Merge adjacent chunks below this token threshold when possible",
    )
    parser.add_argument(
        "--recursive-split",
        action="store_true",
        help="Split oversized direct section bodies when using --splitter section",
    )
    parser.add_argument(
        "--block-config",
        action="append",
        default=[],
        metavar="KIND[:isolated][:nosplit][:TOKENS]",
        help="Per-block-kind config (e.g., table:500:nosplit:isolated); "
        "order-insensitive. Flags: isolated, nosplit; integer sets max_tokens",
    )
    return parser


def main() -> None:
    """CLI entry point: parse arguments, split a file, and output results."""
    parser = build_parser()
    args = parser.parse_args()
    input_path = Path(args.input)

    block_options = _parse_block_configs(args.block_config)

    chunks = lumber(
        input_path,
        format=args.input_format,
        max_tokens=args.max_tokens,
        ideal_max_tokens_ratio=args.ideal_max_tokens_ratio,
        merge_below_tokens=args.merge_below_tokens,
        block_options=block_options,  # ty: ignore[invalid-argument-type]
        tokenizer=args.tokenizer,
        splitter=args.splitter,
        recursive_split=args.recursive_split,
        document_metadata={"path": str(input_path.resolve())},
    )

    payload = json.dumps(
        {
            "document": chunks[0].document_title if chunks else "Anonymous",
            "chunk_count": len(chunks),
            "chunks": [asdict(chunk) for chunk in chunks],
        },
        ensure_ascii=False,
        indent=2,
    )

    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Wrote {len(chunks)} chunks to {args.output}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
