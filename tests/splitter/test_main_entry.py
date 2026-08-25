from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from lumberjack.serialization import CHUNK_SCHEMA_VERSION
from lumberjack.splitter.__main__ import main

MARKDOWN = "\n\n".join(
    [
        "# Guide",
        *[
            f"Paragraph {index} with enough words to occupy tokens."
            for index in range(12)
        ],
    ]
)


def _write_markdown(tmp_path: Path) -> Path:
    doc = tmp_path / "guide.md"
    doc.write_text(MARKDOWN, encoding="utf-8")
    return doc


def test_main_prints_chunk_result_json(tmp_path: Path, capsys, monkeypatch) -> None:
    doc = _write_markdown(tmp_path)

    monkeypatch.setattr(sys, "argv", ["python -m lumberjack.splitter", str(doc)])
    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == CHUNK_SCHEMA_VERSION
    assert payload["document"] == "Guide"
    assert payload["chunk_count"] == len(payload["chunks"])
    first = payload["chunks"][0]
    assert first["chunk_id"]
    assert first["document_title"] == "Guide"
    assert first["document_path"] == str(doc)


def test_main_max_tokens_controls_chunk_count(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    doc = _write_markdown(tmp_path)
    counts = {}
    for budget in ("40", "4000"):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "python -m lumberjack.splitter",
                str(doc),
                "--max-tokens",
                budget,
            ],
        )
        main()
        payload = json.loads(capsys.readouterr().out)
        counts[budget] = payload["chunk_count"]
    assert counts["40"] > counts["4000"]
    assert counts["4000"] == 1


def test_main_selects_splitter_variant(tmp_path: Path, capsys, monkeypatch) -> None:
    doc = _write_markdown(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m lumberjack.splitter",
            str(doc),
            "--splitter",
            "exact-sibling",
            "--max-tokens",
            "60",
        ],
    )
    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == CHUNK_SCHEMA_VERSION
    assert payload["chunk_count"] >= 2


def test_main_reads_stdin_text(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("# Stdin\n\nbody text\n"))
    monkeypatch.setattr(sys, "argv", ["python -m lumberjack.splitter", "-"])
    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["document"] == "Stdin"
    assert payload["chunk_count"] == 1


def test_main_record_splitter_for_csv(tmp_path: Path, capsys, monkeypatch) -> None:
    doc = tmp_path / "people.csv"
    doc.write_text("name,age\nalice,30\nbob,25\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m lumberjack.splitter",
            str(doc),
            "--format",
            "csv",
            "--splitter",
            "record",
        ],
    )
    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == CHUNK_SCHEMA_VERSION
    assert payload["chunk_count"] >= 1


def test_main_rejects_missing_file(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["python -m lumberjack.splitter", "no-such.md"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert str(excinfo.value.code) == "error: no such file: no-such.md"
