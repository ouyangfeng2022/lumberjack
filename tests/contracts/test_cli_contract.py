from __future__ import annotations

import argparse

from lumberjack._internal.pipeline import BUILTIN_SPLITTER_NAMES
from lumberjack.cli import build_parser


def _action(parser: argparse.ArgumentParser, dest: str) -> argparse.Action:
    return next(action for action in parser._actions if action.dest == dest)


def test_cli_public_defaults_and_choices() -> None:
    parser = build_parser()

    assert _action(parser, "input_format").default == "auto"
    assert set(_action(parser, "input_format").choices or ()) == {
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
    }
    assert _action(parser, "tokenizer").default == "approx"
    assert _action(parser, "tokenizer").choices == (
        "approx",
        "tiktoken",
        "transformers",
    )
    assert _action(parser, "splitter").default == "section"
    assert set(_action(parser, "splitter").choices or ()) == {
        "sibling",
        "incremental-sibling",
        "exact-sibling",
        "subtree",
        "incremental-subtree",
        "exact-subtree",
        "section",
        "incremental-section",
        "exact-section",
        "record",
    }
    assert set(BUILTIN_SPLITTER_NAMES) == set(_action(parser, "splitter").choices or ())
    assert _action(parser, "max_tokens").default == 1200
    assert _action(parser, "ideal_max_tokens_ratio").default == 0.8
    assert _action(parser, "merge_below_ratio").default == 0.125
    assert _action(parser, "heading_sensitive").default is True
    assert _action(parser, "trace_stage").default == []
    assert _action(parser, "trace_max_bytes").default == 1_048_576
    assert "render_headings" not in {action.dest for action in parser._actions}


def test_cli_help_assigns_counting_mode_to_splitter() -> None:
    help_text = build_parser().format_help()
    normalized_help = " ".join(help_text.split())

    assert "Tokenizer engine used to encode and count text" in help_text
    assert "Counting mode is selected by --splitter" in help_text
    assert "unprefixed names use incremental counting" in normalized_help
    assert "--token-counter" not in help_text
    assert "--recursive" in help_text
    assert "--jsonl" in help_text
    assert "--trace-stage" in help_text
    assert "--block.table.max-tokens" in help_text
    assert "--block.table.repeat-header" in help_text
    assert "--block-config" not in help_text
    assert "--block-config-json" not in help_text
