"""Smoke tests for the runnable end-to-end examples (plan module T5.2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _run(name: str, env_extra: dict[str, str] | None = None) -> dict:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    completed = subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / name)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    return json.loads(completed.stdout)


def test_technical_document_example_reports_provenance() -> None:
    summary = _run("technical_document.py")

    assert summary["case"] == "technical_document"
    structure = summary["structure_aware"]
    assert structure["chunk_count"] >= 2
    assert structure["budget_violations"] == 0
    provenance = structure["provenance"]
    assert provenance
    # every nested chunk carries the document h1 as an ancestor heading
    assert any(
        heading[1] == "Platform Guide"
        for entry in provenance
        for heading in entry["ancestor_headings"]
    )
    assert summary["naive_text_split"]["chunk_count"] >= 1
    assert summary["naive_text_split"]["heading_provenance"] is None


def test_table_chunking_example_toggles_header_repetition() -> None:
    summary = _run("table_chunking.py")

    assert summary["case"] == "table_chunking"
    with_header = summary["repeat_header_default"]
    without_header = summary["repeat_header_off"]
    unsplittable = summary["unsplittable_table"]

    assert with_header["table_chunk_count"] >= 2
    assert with_header["every_table_chunk_repeats_header"] is True
    assert with_header["over_budget_chunks"] == 0

    assert without_header["every_table_chunk_repeats_header"] is False

    assert unsplittable["table_chunk_count"] == 1
    assert unsplittable["over_budget_chunks"] == 1


def test_incremental_counting_example_compares_modes() -> None:
    summary = _run(
        "incremental_counting.py",
        env_extra={"LUMBERJACK_EXAMPLE_TOKENIZER": "approx"},
    )

    assert summary["case"] == "incremental_counting"
    exact = summary["exact_section"]
    incremental = summary["incremental_section"]

    assert exact["chunk_count"] == incremental["chunk_count"]
    assert exact["total_tokens"] == incremental["total_tokens"]
    # Exact planning re-encodes the growing rendered candidate at every
    # budget decision (identical strings deduplicated per split), so its
    # encoded text volume dominates even when its call count does not.
    assert exact["tokenizer_count_chars"] > incremental["tokenizer_count_chars"]
    assert (
        exact["mean_estimate_error_pct"]
        <= incremental["mean_estimate_error_pct"] + 1e-6
    )
    assert incremental["mean_estimate_error_pct"] >= 0.0
