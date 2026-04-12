from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import MarkdownParser, MarkdownSplitter, create_tokenizer
from .models import Chunk, SplitOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AST-driven markdown splitter")
    parser.add_argument("input", help="Path to a markdown file")
    parser.add_argument("--output", help="Optional output file path")
    parser.add_argument(
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
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--min-tokens", type=int, default=200)
    return parser


def chunk_to_dict(chunk: Chunk) -> dict[str, object]:
    return {
        "text": chunk.text,
        "token_count": chunk.token_count,
        "headings": list(chunk.headings),
        "section_level": chunk.section_level,
    }


def render_markdown(chunks: list[Chunk]) -> str:
    rendered: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        rendered.append(f"<!-- chunk {index} tokens={chunk.token_count} -->")
        rendered.append(chunk.text)
    return "\n\n".join(rendered).strip()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    markdown_text = input_path.read_text(encoding="utf-8")

    tokenizer = create_tokenizer(args.tokenizer)
    markdown_parser = MarkdownParser()
    splitter = MarkdownSplitter(tokenizer=tokenizer)
    document = markdown_parser.parse(markdown_text, document_title=input_path.name)
    chunks = splitter.split(
        document,
        SplitOptions(max_tokens=args.max_tokens, min_tokens=args.min_tokens),
    )

    if args.format == "markdown":
        payload = render_markdown(chunks)
    else:
        payload = json.dumps(
            {
                "document": input_path.name,
                "chunk_count": len(chunks),
                "chunks": [chunk_to_dict(chunk) for chunk in chunks],
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
