from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lumberjack.block import MarkdownTableConfig
from lumberjack.cli import _parse_cli_block_options, build_parser, main


def test_cli_validates_block_configs_against_detected_html_format(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        "<h1>Guide</h1><table><tr><th>A</th></tr><tr><td>1</td></tr></table>",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lumber",
            str(html_path),
            "--max-tokens",
            "500",
            "--block",
            "html_table:isolated=true",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["document"] == "Guide"
    assert payload["metadata"] == {}
    assert payload["reference_definitions"] == {}
    assert payload["chunk_count"] >= 1


def test_cli_parses_compact_block_options() -> None:
    args = build_parser().parse_args(
        [
            "guide.md",
            "--block",
            "table:max-tokens=600,split=false,repeat-header=false",
            "--block",
            "code_fence:isolated=true",
        ]
    )

    configs = {str(config.kind): config for config in _parse_cli_block_options(args)}

    table = configs["table"]
    assert isinstance(table, MarkdownTableConfig)
    assert table.max_tokens == 600
    assert table.split is False
    assert table.repeat_header is False
    assert table.isolated is False
    assert configs["code_fence"].isolated is True
    assert configs["code_fence"].split is True


def test_cli_block_options_reject_invalid_values_and_legacy_flags() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["guide.md", "--block", "table:split=yes"])
    zero_budget = parser.parse_args(
        ["guide.md", "--block", "table:isolated=true,max-tokens=0"]
    )
    with pytest.raises(ValueError, match="positive integer"):
        _parse_cli_block_options(zero_budget)
    with pytest.raises(SystemExit):
        parser.parse_args(["guide.md", "--block.table.split", "true"])


def test_cli_rejects_duplicate_block_kinds() -> None:
    args = build_parser().parse_args(
        [
            "guide.md",
            "--block",
            "table:split=false",
            "--block",
            "table:isolated=true",
        ]
    )

    with pytest.raises(ValueError, match="duplicate block config"):
        _parse_cli_block_options(args)


def test_cli_includes_only_requested_bounded_trace_stages(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    markdown_path = tmp_path / "guide.md"
    markdown_path.write_text("# Guide\n\nBody", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["lumber", str(markdown_path), "--trace-stage", "document"],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert list(payload["trace"]) == ["document"]
    assert payload["trace"]["document"]["title"] == "Guide"


def test_cli_auto_detects_csv_with_explicit_record_splitter(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    csv_path = tmp_path / "people.csv"
    csv_path.write_text("name,age\nAda,36\nGrace,85\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["lumber", str(csv_path), "--splitter", "record", "--max-tokens", "100"],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["document"] == "people"
    assert payload["chunks"][0]["chunk_type"] == "record"
    assert [
        location["row_start"] for location in payload["chunks"][0]["source_locations"]
    ] == [
        2,
        3,
    ]


def test_cli_directory_emits_jsonl_and_keeps_progress_off_stdout(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    (tmp_path / "a.md").write_text("# A", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["lumber", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.out.splitlines()]
    assert [record["status"] for record in records] == ["success", "success"]
    assert all(
        record["result"]["schema_version"] == "lumberjack.chunk.v1"
        for record in records
    )
    assert "processed" in captured.err


def test_cli_single_failed_input_exits_cleanly(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    missing = tmp_path / "missing.md"
    monkeypatch.setattr(sys, "argv", ["lumber", str(missing), "--max-tokens", "100"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FileNotFoundError" in captured.err
    assert "Traceback" not in captured.err


def test_cli_batch_failure_reflected_in_exit_code(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    (tmp_path / "good.md").write_text("# Good", encoding="utf-8")
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe\x00broken")
    monkeypatch.setattr(sys, "argv", ["lumber", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert {record["status"] for record in records} == {"success", "error"}


def test_cli_empty_batch_exit_code_and_silent_stdout(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr(sys, "argv", ["lumber", str(empty_dir)])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no input files matched" in captured.err


def test_cli_output_dir_mirrors_relative_paths(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    (docs / "sub").mkdir(parents=True)
    (docs / "a.md").write_text("# A", encoding="utf-8")
    (docs / "sub" / "a.md").write_text("# Sub A", encoding="utf-8")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        ["lumber", str(docs), "--recursive", "--output-dir", str(out_dir)],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 0
    top = json.loads((out_dir / "a.md.json").read_text(encoding="utf-8"))
    nested = json.loads((out_dir / "sub" / "a.md.json").read_text(encoding="utf-8"))
    assert top["status"] == "success"
    assert nested["status"] == "success"
    assert top["input_id"] != nested["input_id"]


def test_cli_directory_batch_skips_unknown_suffixes_and_hidden_files(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    (tmp_path / "a.md").write_text("# A", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01binary")
    (tmp_path / ".hidden.md").write_text("# H", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["lumber", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [Path(r["input_id"]).name for r in records] == ["a.md"]


def test_cli_trace_rides_beside_the_chunk_payload(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    guide = tmp_path / "guide.md"
    guide.write_text("# Guide\n\nBody", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["lumber", str(guide), "--trace-stage", "document"]
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == ["result", "trace"]
    assert payload["result"]["schema_version"] == "lumberjack.chunk.v1"
    assert "trace" not in payload["result"]
    assert payload["trace"]["document"]["title"] == "Guide"
