from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.fetch_parser_corpora import fetch_corpora


def test_fetch_corpora_merges_partial_fetches_into_lock(tmp_path: Path) -> None:
    sources: list[dict[str, object]] = []
    for source_id in ("first", "second"):
        payload = f"{source_id} corpus".encode()
        source_file = tmp_path / f"{source_id}.json"
        source_file.write_bytes(payload)
        sources.append(
            {
                "id": source_id,
                "kind": "commonmark-json",
                "url": source_file.as_uri(),
                "target": "spec.json",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"dataset_version": "test", "sources": sources}),
        encoding="utf-8",
    )
    corpus_root = tmp_path / "corpus"

    fetch_corpora(corpus_root, source_ids={"first"}, manifest_path=manifest)
    lock = fetch_corpora(
        corpus_root,
        source_ids={"second"},
        manifest_path=manifest,
    )

    assert set(lock["sources"]) == {"first", "second"}
    persisted = json.loads((corpus_root / "corpus-lock.json").read_text())
    assert persisted["sources"] == lock["sources"]


def test_fetch_corpora_rejects_manifest_paths_outside_roots(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset_version": "test",
                "sources": [
                    {
                        "id": "../outside",
                        "kind": "commonmark-json",
                        "url": (tmp_path / "unused.json").as_uri(),
                        "target": "spec.json",
                        "sha256": "0" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes its root"):
        fetch_corpora(tmp_path / "corpus", manifest_path=manifest)
