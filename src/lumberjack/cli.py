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
from .block import BlockOption
from .models import SplitResult
from .parser import InputFormat
from .serialization import split_result_to_dict

_BLOCK_FIELDS = frozenset({"isolated", "split", "max_tokens", "repeat_header"})


def _parse_bool(value: str) -> bool:
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("must be true or false")


def _parse_block_argument(value: str) -> tuple[str, dict[str, object]]:
    """Parse ``KIND:KEY=VALUE,...`` into one external block mapping."""
    kind, separator, settings = value.partition(":")
    kind = kind.strip().lower()
    if not kind or not separator or not settings.strip():
        raise argparse.ArgumentTypeError("expected KIND:KEY=VALUE[,KEY=VALUE...]")

    config: dict[str, object] = {}
    for assignment in settings.split(","):
        key, equals, raw_value = assignment.partition("=")
        field = key.strip().lower().replace("-", "_")
        if not equals or not field or not raw_value.strip():
            raise argparse.ArgumentTypeError(
                f"invalid block setting {assignment!r}; expected KEY=VALUE"
            )
        if field not in _BLOCK_FIELDS:
            valid = ", ".join(sorted(name.replace("_", "-") for name in _BLOCK_FIELDS))
            raise argparse.ArgumentTypeError(
                f"unknown block setting {key!r}; valid settings: {valid}"
            )
        if field in config:
            raise argparse.ArgumentTypeError(f"duplicate block setting: {key!r}")
        if field == "max_tokens":
            try:
                config[field] = int(raw_value)
            except ValueError as error:
                raise argparse.ArgumentTypeError(
                    "max-tokens must be an integer"
                ) from error
        else:
            config[field] = _parse_bool(raw_value.strip())
    return kind, config


def _parse_cli_block_options(args: argparse.Namespace) -> list[BlockOption]:
    raw: dict[str, dict[str, object]] = {}
    for kind, config in args.block:
        if kind in raw:
            raise ValueError(f"duplicate block config for kind: {kind!r}")
        raw[kind] = config
    return parse_block_config_mapping(raw) or []


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all split options."""
    parser = argparse.ArgumentParser(
        description="Markdown, HTML, DOCX, text, CSV/TSV, JSONL, and log document splitter"
    )
    parser.add_argument(
        "input", help="Path, directory, or glob of supported document files"
    )
    input_options = parser.add_argument_group("input")
    input_options.add_argument(
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
        metavar="FORMAT",
        help="Input format (default: auto-detect from file extension)",
    )
    output_options = parser.add_argument_group("output")
    output_options.add_argument("-o", "--output", help="Optional output file path")
    output_options.add_argument(
        "--jsonl", action="store_true", help="Emit one result record per line"
    )

    batch_options = parser.add_argument_group("batch processing")
    batch_options.add_argument(
        "--output-dir", help="Write one JSON result per input directory"
    )
    batch_options.add_argument(
        "--recursive", action="store_true", help="Recurse when input is a directory"
    )
    batch_options.add_argument(
        "--overwrite", action="store_true", help="Allow replacing files in --output-dir"
    )
    batch_options.add_argument(
        "--fail-fast", action="store_true", help="Stop after the first input failure"
    )

    split_options = parser.add_argument_group("splitting")
    split_options.add_argument(
        "--tokenizer",
        choices=("approx", "tiktoken", "transformers"),
        default="approx",
        metavar="ENGINE",
        help="Tokenizer engine used to encode and count text. Counting mode is "
        "selected by --splitter; unprefixed names use incremental counting and "
        "exact-* selects full recounting.",
    )
    split_options.add_argument(
        "--splitter",
        choices=BUILTIN_SPLITTER_NAMES,
        default="section",
        metavar="NAME",
        help=(
            "Splitter implementation. 'sibling'/'subtree'/'section' default "
            "to incremental counting; use 'exact-*' for full recounting. "
            "Use 'record' for CSV/TSV, JSONL, and log files."
        ),
    )
    split_options.add_argument(
        "--max-tokens", type=int, default=1200, help="Maximum tokens per chunk"
    )

    tuning_options = parser.add_argument_group("advanced splitting")
    tuning_options.add_argument(
        "--ideal-max-tokens-ratio",
        type=float,
        default=0.8,
        help="Preferred split budget as a ratio of --max-tokens",
    )
    tuning_options.add_argument(
        "--merge-below-ratio",
        type=float,
        default=0.125,
        help="Tail-fragment merge threshold as a fraction of --max-tokens "
        "in [0.0, 1.0); 0 disables merging (default: 0.125)",
    )
    tuning_options.add_argument(
        "--heading-sensitive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include the chunk's external heading-path tokens in split budgets "
        "(default: enabled). Headings are always returned as metadata.",
    )
    tuning_options.add_argument(
        "--max-heading-level",
        type=int,
        default=None,
        help="Maximum heading level to keep as chunk section context. "
        "Deeper headings are rendered as body text.",
    )
    block_options = parser.add_argument_group("block handling")
    block_options.add_argument(
        "--block",
        action="append",
        default=[],
        type=_parse_block_argument,
        metavar="KIND:SETTING,...",
        help=(
            "Configure one block kind; repeatable. Settings: isolated=BOOL, "
            "split=BOOL, max-tokens=N, and table-only repeat-header=BOOL"
        ),
    )

    trace_options = parser.add_argument_group("diagnostics")
    trace_options.add_argument(
        "--trace-stage",
        action="append",
        choices=TRACE_STAGES,
        default=[],
        help="Include one pipeline trace stage in JSON output; repeatable. "
        "Default: no trace stages.",
    )
    trace_options.add_argument(
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
