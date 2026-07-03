from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from . import lumber
from .core.options import parse_cli_block_configs
from .core.parsers import create_parser
from .formats import detect_format


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all split options."""
    parser = argparse.ArgumentParser(
        description="Markdown / HTML / DOCX document splitter"
    )
    parser.add_argument(
        "input", help="Path to a Markdown (.md), HTML (.html), or DOCX (.docx) file"
    )
    parser.add_argument(
        "--input-format",
        choices=("auto", "markdown", "html", "docx"),
        default="auto",
        help="Input format (default: auto-detect from file extension)",
    )
    parser.add_argument("-o", "--output", help="Optional output file path")
    parser.add_argument(
        "--tokenizer",
        choices=("approx", "tiktoken", "transformers"),
        default="approx",
        help="Tokenizer implementation. 'approx' is an exact-count engine "
        "(len(text) // 4, fully recounts rendered text); 'tiktoken' and "
        "'transformers' use the additive incremental estimate path.",
    )
    parser.add_argument(
        "--splitter",
        choices=(
            "recursive",
            "section",
            "exact-recursive",
            "incremental-recursive",
            "exact-section",
            "incremental-section",
        ),
        default="recursive",
        help=(
            "Splitter implementation. 'recursive'/'section' default to the exact "
            "(full-recount) variants; 'incremental-*' use an additive estimate + "
            "8-char separator-delta window."
        ),
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
        help="Merge adjacent chunks below this token threshold when possible "
        "(use -1 to disable merging)",
    )
    parser.add_argument(
        "--no-render-headings",
        action="store_true",
        help="Omit the chunk's common heading breadcrumb from the rendered body. "
        "The split budget is based on the rendered body.",
    )
    parser.add_argument(
        "--max-heading-level",
        type=int,
        default=None,
        help="Maximum heading level to parse as sections (Markdown only). "
        "Headings deeper than this are treated as regular paragraphs.",
    )
    parser.add_argument(
        "--block-config",
        action="append",
        default=[],
        metavar="KIND[:isolated][:nosplit][:TOKENS]",
        help="Per-block-kind config (e.g., table:500:nosplit:isolated); "
        "order-insensitive. Flags: isolated, nosplit; integer sets max_tokens",
    )
    parser.add_argument(
        "--block-config-json",
        default="",
        metavar="JSON",
        help="Structured per-block-kind config JSON. Overrides --block-config "
        "for matching kinds.",
    )
    return parser


def main() -> None:
    """CLI entry point: parse arguments, split a file, and output results."""
    parser = build_parser()
    args = parser.parse_args()
    input_path = Path(args.input)

    input_format = detect_format(input_path, args.input_format)
    parser_impl = create_parser(input_format)
    block_options = parse_cli_block_configs(
        args.block_config,
        block_kinds=parser_impl.block_kinds,
        json_config=args.block_config_json,
    )

    chunks = lumber(
        input_path,
        format=input_format,
        max_tokens=args.max_tokens,
        ideal_max_tokens_ratio=args.ideal_max_tokens_ratio,
        merge_below_tokens=args.merge_below_tokens,
        block_options=block_options,
        tokenizer=args.tokenizer,
        splitter=args.splitter,
        render_headings=not args.no_render_headings,
        max_heading_level=args.max_heading_level,
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
