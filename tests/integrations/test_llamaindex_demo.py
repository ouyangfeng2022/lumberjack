from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_llamaindex_demo_runs_full_pipeline(tmp_path: Path) -> None:
    pytest.importorskip("llama_index.core")
    source = tmp_path / "guide.md"
    source.write_text(
        "# Installation\n\nInstall Lumberjack before building an index.\n\n"
        "# Retrieval\n\nLumberjack preserves chunk provenance for retrieval.\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "examples/llama_index_demo.py",
            str(source),
            "--query",
            "What does Lumberjack preserve?",
            "--max-tokens",
            "40",
            "--top-k",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(completed.stdout)

    assert output["chunk_count"] == 2
    assert len(output["retrieved"]) == 2
    assert {item["chunk_id"] for item in output["retrieved"]} == {
        chunk["chunk_id"] for chunk in output["chunks"]
    }
    assert all("source_locations" in item["metadata"] for item in output["chunks"])
    assert "Lumberjack preserves chunk provenance" in output["response"]
