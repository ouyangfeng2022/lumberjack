from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .api import lumber

if TYPE_CHECKING:
    from .models import Chunk


def _parse_block_max_tokens(pairs: list[str]) -> dict[str, int]:
    """Parse ``KIND:TOKENS`` strings into a ``{kind: tokens}`` dict."""
    result: dict[str, int] = {}
    for pair in pairs:
        if ":" not in pair:
            raise ValueError(
                f"Invalid format: {pair!r} (expected KIND:TOKENS, e.g. paragraph:800)"
            )
        kind, _, value = pair.partition(":")
        kind = kind.strip().lower()
        try:
            tokens = int(value.strip())
        except ValueError:
            raise ValueError(
                f"Invalid token count in: {pair!r} (expected KIND:TOKENS)"
            ) from None
        if tokens <= 0:
            raise ValueError(f"Token count must be positive in: {pair!r}")
        result[kind] = tokens
    return result

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
        "--overlap-tokens",
        type=int,
        default=0,
        help="Token overlap for text fallback splits",
    )
    parser.add_argument(
        "--recursive-split",
        action="store_true",
        help="Split oversized direct section bodies when using --splitter section",
    )
    parser.add_argument(
        "--no-isolate-front-matter",
        action="store_true",
        help="Do not isolate front matter as the first chunk",
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
    parser.add_argument(
        "--split-oversized-max-tokens",
        action="append",
        default=[],
        metavar="KIND:TOKENS",
        help="Override max_tokens for a specific block kind when splitting oversized blocks (e.g., paragraph:800); repeat for multiple kinds",
    )
    parser.add_argument(
        "--disable-lheading",
        action="store_true",
        help="Disable markdown-it setext heading parsing via parser.disable('lheading')",
    )
    parser.add_argument(
        "--standalone-block",
        action="append",
        default=None,
        choices=(
            "paragraph",
            "blockquote",
            "list",
            "table",
            "code_block",
            "code_fence",
            "html_block",
        ),
        help="Block kind that must be emitted as an independent chunk; repeat to add multiple (default: table code_block code_fence)",
    )
    parser.add_argument(
        "--no-standalone-blocks",
        action="store_true",
        help="Disable all standalone block isolation",
    )
    return parser


def render_markdown(chunks: list[Chunk]) -> str:
    """Render chunks as Markdown with HTML comment metadata delimiters."""
    rendered: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        rendered.append(f"<!-- chunk {index} tokens={chunk.token_count} -->")
        rendered.append(chunk.body)
    return "\n\n".join(rendered).strip()


def main() -> None:
    """CLI entry point: parse arguments, split a Markdown file, and output results."""
    parser = build_parser()
    args = parser.parse_args()
    input_path = Path(args.input)
    text = input_path.read_text(encoding="utf-8")
    standalone_blocks: frozenset[str]
    if args.no_standalone_blocks:
        standalone_blocks = frozenset()
    elif args.standalone_block is not None:
        standalone_blocks = frozenset(args.standalone_block)
    else:
        standalone_blocks = frozenset({"table", "code_block", "code_fence"})

    split_overrides = _parse_block_max_tokens(args.split_oversized_max_tokens)
    chunks = lumber(
        text,
        max_tokens=args.max_tokens,
        ideal_max_tokens_ratio=args.ideal_max_tokens_ratio,
        merge_below_tokens=args.merge_below_tokens,
        overlap_tokens=args.overlap_tokens,
        isolate_front_matter=not args.no_isolate_front_matter,
        split_oversized_blocks=frozenset(args.split_oversized_block),
        split_oversized_blocks_max_tokens=split_overrides or None,
        standalone_blocks=standalone_blocks,
        disable_lheading=args.disable_lheading,
        tokenizer=args.tokenizer,
        parser=args.parser,
        splitter=args.splitter,
        recursive_split=args.recursive_split,
        document_metadata={"path": str(input_path.resolve())},
    )

    if args.format == "markdown":
        payload = render_markdown(chunks)
    else:
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
