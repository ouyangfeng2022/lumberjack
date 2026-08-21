from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import cast

from ._internal.formats import detect_format
from ._internal.options import parse_block_config_mapping
from ._internal.pipeline import BUILTIN_SPLITTER_NAMES, split_source, trace_source
from ._internal.trace import TRACE_STAGES, TraceStage, select_trace_stages
from .block import BlockKind, BlockOption
from .models import SplitResult
from .parser import InputFormat
from .serialization import split_result_to_dict

_COMMON_BLOCK_FIELDS = ("isolated", "split", "max_tokens")
_TABLE_BLOCK_FIELDS = (*_COMMON_BLOCK_FIELDS, "repeat_header")


def _parse_bool(value: str) -> bool:
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("must be true or false")


def _block_option_dest(kind: BlockKind, field: str) -> str:
    return f"block_{kind.value}_{field}"


def _add_block_config_arguments(parser: argparse._ActionsContainer) -> None:
    """Register explicit dotted block configuration options."""
    for kind in BlockKind:
        fields = (
            _TABLE_BLOCK_FIELDS
            if kind in {BlockKind.TABLE, BlockKind.HTML_TABLE}
            else _COMMON_BLOCK_FIELDS
        )
        for field in fields:
            option = f"--block.{kind.value}.{field.replace('_', '-')}"
            parser.add_argument(
                option,
                dest=_block_option_dest(kind, field),
                default=None,
                type=int if field == "max_tokens" else _parse_bool,
                metavar="TOKENS" if field == "max_tokens" else "BOOL",
                help=f"Set {kind.value}.{field.replace('_', '-')}",
            )


def _parse_cli_block_options(args: argparse.Namespace) -> list[BlockOption]:
    raw: dict[str, dict[str, object]] = {}
    for kind in BlockKind:
        fields = (
            _TABLE_BLOCK_FIELDS
            if kind in {BlockKind.TABLE, BlockKind.HTML_TABLE}
            else _COMMON_BLOCK_FIELDS
        )
        config = {
            field: value
            for field in fields
            if (value := getattr(args, _block_option_dest(kind, field))) is not None
        }
        if config:
            raw[kind.value] = config
    return parse_block_config_mapping(raw) or []


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all split options."""
    parser = argparse.ArgumentParser(
        description="Markdown, HTML, DOCX, text, CSV/TSV, JSONL, and log document splitter"
    )
    parser.add_argument(
        "input", help="Path, directory, or glob of supported document files"
    )
    parser.add_argument(
        "--input-format",
        choices=(
            "auto",
            "markdown",
            "html",
            "docx",
            "text",
            "log",
            "csv",
            "tsv",
            "json",
            "jsonl",
            "xml",
            "yaml",
            "xlsx",
            "toml",
            "sqlite",
            "sql",
            "python",
            "javascript",
            "typescript",
            "bash",
            "c",
            "cpp",
            "csharp",
            "go",
            "java",
            "kotlin",
            "lua",
            "php",
            "ruby",
            "rust",
            "swift",
            "zig",
            "notebook",
        ),
        default="auto",
        help="Input format (default: auto-detect from file extension)",
    )
    parser.add_argument("-o", "--output", help="Optional output file path")
    parser.add_argument(
        "--output-dir", help="Write one JSON result per input directory"
    )
    parser.add_argument(
        "--recursive", action="store_true", help="Recurse when input is a directory"
    )
    parser.add_argument(
        "--jsonl", action="store_true", help="Emit one result record per line"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Allow replacing files in --output-dir"
    )
    parser.add_argument(
        "--fail-fast", action="store_true", help="Stop after the first input failure"
    )
    parser.add_argument(
        "--tokenizer",
        choices=("approx", "tiktoken", "transformers"),
        default="approx",
        help="Tokenizer engine used to encode and count text. Counting mode is "
        "selected by --splitter; unprefixed names use incremental counting and "
        "exact-* selects full recounting.",
    )
    parser.add_argument(
        "--splitter",
        choices=BUILTIN_SPLITTER_NAMES,
        default="section",
        help=(
            "Splitter implementation. 'sibling'/'subtree'/'section' default "
            "to incremental counting; use 'exact-*' for full recounting. "
            "Use 'record' for CSV/TSV, JSONL, and log files."
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
        "--merge-below-ratio",
        type=float,
        default=0.125,
        help="Tail-fragment merge threshold as a fraction of --max-tokens "
        "in [0.0, 1.0); 0 disables merging (default: 0.125)",
    )
    parser.add_argument(
        "--heading-sensitive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include the chunk's external heading-path tokens in split budgets "
        "(default: enabled). Headings are always returned as metadata.",
    )
    parser.add_argument(
        "--max-heading-level",
        type=int,
        default=None,
        help="Maximum heading level to keep as chunk section context. "
        "Deeper headings are rendered as body text.",
    )
    block_options = parser.add_argument_group("block configuration")
    block_options.description = (
        "Configure built-in block kinds with --block.<kind>.<field> VALUE. "
        "Fields: isolated, split, max-tokens; table and html_table also support "
        "repeat-header. Boolean values must be true or false."
    )
    _add_block_config_arguments(block_options)
    parser.add_argument(
        "--trace-stage",
        action="append",
        choices=TRACE_STAGES,
        default=[],
        help="Include one pipeline trace stage in JSON output; repeatable. "
        "Default: no trace stages.",
    )
    parser.add_argument(
        "--trace-max-bytes",
        type=int,
        default=1_048_576,
        help="Maximum serialized trace payload size (default: 1048576)",
    )
    return parser


def main() -> None:
    """CLI entry point: parse arguments, split a file, and output results."""
    parser = build_parser()
    args = parser.parse_args()
    input_paths = _expand_inputs(args.input, recursive=args.recursive)
    batch_mode = (
        len(input_paths) != 1 or Path(args.input).is_dir() or _is_glob(args.input)
    )
    if args.output and (batch_mode or args.jsonl or args.output_dir):
        parser.error(
            "--output only supports one non-JSONL input; use --output-dir for batches"
        )
    if args.output_dir and args.output:
        parser.error("--output-dir cannot be combined with --output")

    try:
        block_options = _parse_cli_block_options(args)
    except (TypeError, ValueError) as error:
        parser.error(str(error))

    records = []
    for input_path in input_paths:
        try:
            result, trace_payload = _split_one(input_path, args, block_options)
            payload = split_result_to_dict(result)
            if trace_payload is not None:
                payload["trace"] = trace_payload
            record: dict[str, object] = {
                "input_id": str(input_path),
                "status": "success",
                "result": payload,
            }
            _write_batch_file(record, input_path, args)
        except Exception as error:
            record = {
                "input_id": str(input_path),
                "status": "error",
                "error": f"{type(error).__name__}: {error}",
            }
            print(record["error"], file=sys.stderr)
            if args.fail_fast:
                raise
        records.append(record)
        print(f"processed {input_path}", file=sys.stderr)

    if batch_mode or args.jsonl:
        print("\n".join(json.dumps(record, ensure_ascii=False) for record in records))
        return
    payload = json.dumps(records[0]["result"], ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Wrote output to {args.output}", file=sys.stderr)
    else:
        print(payload)


def _is_glob(value: str) -> bool:
    return glob.has_magic(value)


def _expand_inputs(value: str, *, recursive: bool) -> list[Path]:
    path = Path(value)
    if path.is_dir():
        iterator = path.rglob("*") if recursive else path.glob("*")
        return sorted(item for item in iterator if item.is_file())
    if _is_glob(value):
        return sorted(
            Path(item)
            for item in glob.glob(value, recursive=recursive)
            if Path(item).is_file()
        )
    return [path]


def _split_one(
    input_path: Path, args: argparse.Namespace, block_options: list[BlockOption]
) -> tuple[SplitResult, dict[str, object] | None]:
    input_format = detect_format(input_path, args.input_format)
    if args.trace_stage:
        trace = trace_source(
            input_path,
            format=cast(InputFormat, input_format),
            max_tokens=args.max_tokens,
            ideal_max_tokens_ratio=args.ideal_max_tokens_ratio,
            merge_below_ratio=args.merge_below_ratio,
            block_options=block_options,
            tokenizer=args.tokenizer,
            splitter=args.splitter,
            heading_sensitive=args.heading_sensitive,
            max_heading_level=args.max_heading_level,
        )
        return SplitResult(
            document=trace.document, chunks=list(trace.chunks)
        ), select_trace_stages(
            trace,
            cast(list[TraceStage], args.trace_stage),
            max_bytes=args.trace_max_bytes,
        )
    return split_source(
        input_path,
        format=cast(InputFormat, input_format),
        max_tokens=args.max_tokens,
        ideal_max_tokens_ratio=args.ideal_max_tokens_ratio,
        merge_below_ratio=args.merge_below_ratio,
        block_options=block_options,
        tokenizer=args.tokenizer,
        splitter=args.splitter,
        heading_sensitive=args.heading_sensitive,
        max_heading_level=args.max_heading_level,
    ), None


def _write_batch_file(
    record: dict[str, object], input_path: Path, args: argparse.Namespace
) -> None:
    if not args.output_dir:
        return
    destination = Path(args.output_dir) / f"{input_path.name}.json"
    if destination.exists() and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite {destination}; pass --overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
