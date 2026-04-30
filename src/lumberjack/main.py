from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .api import split_markdown_file

if TYPE_CHECKING:
    from .models import Chunk


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all split options."""
    parser = argparse.ArgumentParser(description="Markdown splitter")
    parser.add_argument("input", help="Path to a markdown file")
    parser.add_argument("-o", "--output", help="Optional output file path")
    parser.add_argument(
        "-f",
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format",
    )
    parser.add_argument(
        "--tokenizer",
        choices=("simple", "tiktoken"),
        default="simple",
        help="Tokenizer implementation",
    )
    parser.add_argument(
        "--parser",
        choices=("default", "markdown-it"),
        default="default",
        help="Markdown parser implementation",
    )
    parser.add_argument("--max-tokens", type=int, default=1200, help="Maximum tokens per chunk")
    parser.add_argument("--min-tokens", type=int, default=50, help="Minimum tokens per chunk")
    parser.add_argument(
        "--overlap-tokens",
        type=int,
        default=0,
        help="Token overlap for text fallback splits",
    )
    parser.add_argument(
        "--retain-headings", action="store_true", help="Retain headings in each chunk"
    )
    parser.add_argument(
        "--split-oversized-block",
        action="append",
        default=[],
        choices=(
            "paragraph",
            "blockquote",
            "list",
            "table",
            "code_block",
            "code_fence",
            "html_block",
        ),
        help="Allow splitting oversized blocks of the given kind; repeat the flag to enable multiple kinds",
    )
    return parser


def render_markdown(chunks: list[Chunk]) -> str:
    """Render chunks as Markdown with HTML comment metadata delimiters."""
    rendered: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        rendered.append(f"<!-- chunk {index} tokens={chunk.token_count} -->")
        rendered.append(chunk.text)
    return "\n\n".join(rendered).strip()


def main() -> None:
    """CLI entry point: parse arguments, split a Markdown file, and output results."""
    parser = build_parser()
    args = parser.parse_args()
    input_path = Path(args.input)
    chunks = split_markdown_file(
        input_path,
        max_tokens=args.max_tokens,
        min_tokens=args.min_tokens,
        overlap_tokens=args.overlap_tokens,
        retain_headings=args.retain_headings,
        split_oversized_blocks=tuple(args.split_oversized_block),
        tokenizer=args.tokenizer,
        parser=args.parser,
    )

    if args.format == "markdown":
        payload = render_markdown(chunks)
    else:
        payload = json.dumps(
            {
                "document": input_path.name,
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
