from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_langchain_demo_runs_full_pipeline(tmp_path: Path) -> None:
    pytest.importorskip("langchain_core")
    source = tmp_path / "guide.md"
    source.write_text(
        "# Retrieval\n\nLumberjack preserves source provenance for retrieval.\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "examples/langchain_demo.py",
            str(source),
            "--query",
            "What does Lumberjack preserve?",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(completed.stdout)

    assert output["chunk_count"] == 1
    assert (
        output["retrieved"][0]["body"]
        == "Lumberjack preserves source provenance for retrieval."
    )
    assert (
        output["retrieved"][0]["metadata"]["chunk_id"]
        == output["retrieved"][0]["chunk_id"]
    )
    assert output["response"] == "Offline LangChain demo response."
