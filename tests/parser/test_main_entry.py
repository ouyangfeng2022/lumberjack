from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from lumberjack.parser.__main__ import main
from lumberjack.serialization import DOC_TREE_SCHEMA_VERSION

MARKDOWN = "# Guide\n\nintro paragraph\n\n## Usage\n\nusage paragraph\n"


def test_main_prints_doc_tree_json(tmp_path: Path, capsys, monkeypatch) -> None:
    doc = tmp_path / "guide.md"
    doc.write_text(MARKDOWN, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["python -m lumberjack.parser", str(doc)])
    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == DOC_TREE_SCHEMA_VERSION
    assert payload["title"] == "Guide"
    assert payload["source_path"] == str(doc)
    overview = payload["root"]["children"][0]
    assert overview["title"] == "Guide"
    assert overview["children"][0]["title"] == "Usage"


def test_main_outline_prints_section_tree(tmp_path: Path, capsys, monkeypatch) -> None:
    doc = tmp_path / "guide.md"
    doc.write_text(MARKDOWN, encoding="utf-8")

    monkeypatch.setattr(
        sys, "argv", ["python -m lumberjack.parser", str(doc), "--outline"]
    )
    main()

    outline = capsys.readouterr().out
    assert "title: Guide" in outline
    assert "topology: hierarchical" in outline
    assert "# Guide (line 1): paragraph x1" in outline
    assert "## Usage (line 5): paragraph x1" in outline


def test_main_reads_stdin_text(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("# Stdin\n\nbody\n"))
    monkeypatch.setattr(sys, "argv", ["python -m lumberjack.parser", "-"])
    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == "Stdin"


def test_main_format_override_selects_parser(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    doc = tmp_path / "guide.md"
    doc.write_text(MARKDOWN, encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["python -m lumberjack.parser", str(doc), "--format", "text"],
    )
    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["root"]["children"] == []
    kinds = [block["kind"] for block in payload["root"]["blocks"]]
    assert kinds == ["paragraph"] * 4


def test_main_rejects_missing_file(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["python -m lumberjack.parser", "no-such-file.md"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert str(excinfo.value.code) == "error: no such file: no-such-file.md"
