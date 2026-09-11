from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_haystack_demo_runs_full_pipeline(tmp_path: Path) -> None:
    pytest.importorskip("haystack")
    source = tmp_path / "guide.md"
    source.write_text(
        "# Retrieval\n\nLumberjack preserves source provenance for retrieval.\n",
        encoding="utf-8",
    )
    environment = {**os.environ, "HOME": str(tmp_path / "home")}

    completed = subprocess.run(
        [
            sys.executable,
            "examples/haystack_demo.py",
            str(source),
            "--query",
            "What does Lumberjack preserve?",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
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
    assert "Lumberjack preserves source provenance for retrieval." in output["prompt"]
