from __future__ import annotations

from lumberjack.cli import build_parser


def test_cli_render_headings_defaults_to_true() -> None:
    parser = build_parser()
    args = parser.parse_args(["doc.md"])
    assert args.render_headings is True


def test_cli_no_render_headings_flag_sets_false() -> None:
    parser = build_parser()
    args = parser.parse_args(["doc.md", "--no-render-headings"])
    assert args.render_headings is False


def test_cli_render_headings_flag_keeps_true() -> None:
    parser = build_parser()
    args = parser.parse_args(["doc.md", "--render-headings"])
    assert args.render_headings is True
