from __future__ import annotations

import json
import sys
from pathlib import Path

from lumberjack.cli import main


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
            "--block-config",
            "html_table:isolated",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["document"] == "Guide"
    assert payload["metadata"] == {}
    assert payload["reference_definitions"] == {}
    assert payload["chunk_count"] >= 1


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
