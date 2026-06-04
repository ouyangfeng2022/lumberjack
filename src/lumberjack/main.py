from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .api import lumber
from .core.parser import MarkdownItParser
from .models import BlockHandling

if TYPE_CHECKING:
    from .models import Chunk


def _parse_block_handling(pairs: list[str]) -> dict[str, BlockHandling]:
    """Parse ``KIND:POLICY`` strings into a ``{kind: BlockHandling}`` dict."""
    result: dict[str, BlockHandling] = {}
    for pair in pairs:
        if ":" not in pair:
            raise ValueError(
                f"Invalid format: {pair!r} (expected KIND:POLICY, e.g. table:isolate)"
            )
        kind, _, value = pair.partition(":")
        kind = kind.strip().lower()
        MarkdownItParser.default_registry().validate_kind(kind)
        try:
            result[kind] = BlockHandling(value.strip().lower())
        except ValueError:
            valid = ", ".join(h.value for h in BlockHandling)
            raise ValueError(
                f"Invalid policy in: {pair!r} (valid policies: {valid})"
            ) from None
    return result


def _parse_nosplit_kinds(raw: str) -> frozenset[str]:
    """Parse a comma-separated string of block kinds into a frozenset."""
    if not raw or not raw.strip():
        return frozenset()
    kinds: set[str] = set()
    for part in raw.split(","):
        kind = part.strip().lower()
        if not kind:
            continue
        MarkdownItParser.default_registry().validate_kind(kind)
        kinds.add(kind)
    return frozenset(kinds)


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
        "--block-handling",
        action="append",
        default=[],
        metavar="KIND:POLICY",
        help="Override block merge policy for a specific kind "
        "(e.g., table:isolate); may be repeated. "
        "Policies: default, isolate",
    )
    parser.add_argument(
        "--nosplit-kinds",
        default="",
        metavar="KIND,...",
        help="Comma-separated block kinds that should NOT be split when oversized "
        "(e.g., table,code_fence). Default: all kinds allow splitting.",
    )
    parser.add_argument(
        "--block-max-tokens",
        action="append",
        default=[],
        metavar="KIND:TOKENS",
        help="Override max_tokens for a specific block kind "
        "(e.g., paragraph:800); may be repeated",
    )
    parser.add_argument(
        "--disable-lheading",
        action="store_true",
        help="Disable markdown-it setext heading parsing via parser.disable('lheading')",
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

    # Build block_handling: start from defaults, apply user overrides
    block_handling = dict(MarkdownItParser.default_registry().default_handling())
    if args.block_handling:
        block_handling.update(_parse_block_handling(args.block_handling))

    block_max_tokens = _parse_block_max_tokens(args.block_max_tokens)
    nosplit_kinds = _parse_nosplit_kinds(args.nosplit_kinds)

    chunks = lumber(
        text,
        max_tokens=args.max_tokens,
        ideal_max_tokens_ratio=args.ideal_max_tokens_ratio,
        merge_below_tokens=args.merge_below_tokens,
        overlap_tokens=args.overlap_tokens,
        block_handling=block_handling,
        nosplit_kinds=nosplit_kinds,
        block_max_tokens=block_max_tokens or None,
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
