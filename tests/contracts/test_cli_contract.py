from __future__ import annotations

import argparse

from lumberjack.cli import build_parser
from lumberjack.core.splitter import SPLITTER_REGISTRY


def _action(parser: argparse.ArgumentParser, dest: str) -> argparse.Action:
    return next(action for action in parser._actions if action.dest == dest)


def test_cli_public_defaults_and_choices() -> None:
    parser = build_parser()

    assert _action(parser, "input_format").default == "auto"
    assert _action(parser, "tokenizer").default == "approx"
    assert _action(parser, "tokenizer").choices == (
        "approx",
        "tiktoken",
        "transformers",
    )
    assert _action(parser, "splitter").default == "sibling"
    assert set(_action(parser, "splitter").choices or ()) == set(SPLITTER_REGISTRY)
    assert _action(parser, "max_tokens").default == 1200
    assert _action(parser, "ideal_max_tokens_ratio").default == 0.8
    assert _action(parser, "merge_below_ratio").default == 0.125
    assert _action(parser, "no_render_headings").default is False


def test_cli_help_assigns_counting_mode_to_splitter() -> None:
    help_text = build_parser().format_help()

    assert "Tokenizer engine used to encode and count text" in help_text
    assert "Counting mode is selected by --splitter" in help_text
    assert "incremental-*" in help_text
    assert "tiktoken' and 'transformers' use the additive" not in help_text
    assert "--token-counter" not in help_text
    assert "recursive" not in help_text
