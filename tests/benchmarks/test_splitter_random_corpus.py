from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.splitter_random_corpus import (
    RECOMBINED_MAX_BYTES,
    SHAPES,
    _split_sections,
    _strip_front_matter,
    generate_documents,
    recombine_documents,
)


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def test_generate_documents_is_deterministic() -> None:
    first = generate_documents(
        list(SHAPES), seed=42, count_per_shape=2, budget_tokens=200
    )
    second = generate_documents(
        list(SHAPES), seed=42, count_per_shape=2, budget_tokens=200
    )
    assert [_digest(document.source) for document in first] == [
        _digest(document.source) for document in second
    ]

    other_seed = generate_documents(
        ["wide-flat"], seed=43, count_per_shape=1, budget_tokens=200
    )
    baseline = generate_documents(
        ["wide-flat"], seed=42, count_per_shape=1, budget_tokens=200
    )
    assert other_seed[0].source != baseline[0].source


def test_documents_carry_consistent_sentinel_oracles() -> None:
    documents = generate_documents(
        list(SHAPES), seed=7, count_per_shape=3, budget_tokens=200
    )
    assert len(documents) == len(SHAPES) * 3
    for document in documents:
        assert document.dataset == f"synthetic-{document.shape}"
        assert document.document_id.startswith(f"synthetic-{document.shape}-")
        sentinels = document.required_content + document.protected_content
        assert sentinels
        assert len(set(sentinels)) == len(sentinels)
        assert not set(document.required_content) & set(document.protected_content)
        for sentinel in document.required_content:
            assert sentinel in document.source
        for sentinel in document.protected_content:
            assert f"# {sentinel}" in document.source


def test_shape_profiles_match_their_structural_intent() -> None:
    budget = 200
    deep = generate_documents(
        ["deep-tree"], seed=5, count_per_shape=4, budget_tokens=budget
    )
    assert all(document.profile["max_heading_depth"] >= 4 for document in deep)

    wide = generate_documents(
        ["wide-flat"], seed=5, count_per_shape=4, budget_tokens=budget
    )
    assert all(document.profile["headings"] >= 8 for document in wide)

    long_sections = generate_documents(
        ["long-sections"], seed=5, count_per_shape=4, budget_tokens=budget
    )
    assert all(document.profile["approx_tokens"] > budget for document in long_sections)

    oversized = generate_documents(
        ["oversized-blocks"], seed=5, count_per_shape=4, budget_tokens=budget
    )
    assert any(
        document.profile["max_code_fence_tokens"] > budget for document in oversized
    )

    tiny = generate_documents(
        ["tiny-sections"], seed=5, count_per_shape=4, budget_tokens=budget
    )
    assert all(document.profile["headings"] >= 12 for document in tiny)


def test_edge_degenerate_records_and_covers_all_variants() -> None:
    expected = {"no-headings", "single-giant", "only-code", "long-titles"}
    seen: set[str] = set()
    for seed in range(60):
        documents = generate_documents(
            ["edge-degenerate"], seed=seed, count_per_shape=2, budget_tokens=200
        )
        for document in documents:
            assert document.profile["variant"] in expected
            seen.add(str(document.profile["variant"]))
    assert seen == expected


def test_generate_documents_rejects_unknown_shapes() -> None:
    with pytest.raises(ValueError, match="unknown random splitter corpus shapes"):
        generate_documents(["nonsense"], seed=1, count_per_shape=1, budget_tokens=100)


def test_front_matter_is_stripped() -> None:
    assert (
        _strip_front_matter("---\ntitle: doc\nweight: 3\n---\n\n# Body\n")
        == "\n# Body\n"
    )
    assert _strip_front_matter("# No front matter\n") == "# No front matter\n"


def test_split_sections_drops_unbalanced_fences() -> None:
    balanced = "# A\n\n```python\nx = 1\n```\n\nafter\n"
    assert len(_split_sections(balanced)) == 1

    unbalanced = "# A\n\nbody\n\n```python\ncode\n\n## B\n\nafter\n"
    sections = _split_sections(unbalanced)
    assert len(sections) == 1
    assert sections[0].startswith("## B")


def _write_local_manifest(tmp_path: Path) -> tuple[Path, Path]:
    cases = []
    for index in range(12):
        sections = "\n\n".join(
            f"## Section {index}-{part}\n\n"
            f"Body alpha {index}-{part} with words.\n\n"
            f"Second paragraph beta {index}-{part}."
            for part in range(3)
        )
        front_matter = f"---\ntitle: doc-{index}\n---\n\n" if index % 3 == 0 else ""
        cases.append(
            {
                "id": f"case-{index:02d}",
                "source": f"{front_matter}# Doc {index}\n\n{sections}\n",
                "required_elements": [],
            }
        )
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    manifest = {
        "dataset_version": "test",
        "sources": [
            {
                "id": "local-cases",
                "kind": "local-cases-json",
                "format": "markdown",
                "target": "cases.json",
                "revision": "1",
            }
        ],
    }
    manifest_path = tmp_path / "parser_sources.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, tmp_path / "external"


def test_recombine_documents_is_deterministic_and_bounded(tmp_path: Path) -> None:
    manifest_path, corpus_root = _write_local_manifest(tmp_path)
    first = recombine_documents(
        seed=11, count=4, manifest_path=manifest_path, corpus_root=corpus_root
    )
    second = recombine_documents(
        seed=11, count=4, manifest_path=manifest_path, corpus_root=corpus_root
    )
    assert [_digest(document.source) for document in first] == [
        _digest(document.source) for document in second
    ]
    assert len(first) == 4
    for document in first:
        assert document.dataset == "recombined"
        assert document.shape == "recombined"
        assert document.required_content == ()
        assert document.protected_content == ()
        assert document.min_word_recall == 0.99
        assert len(document.source.encode("utf-8")) <= RECOMBINED_MAX_BYTES
        assert document.profile["headings"] >= 2
        assert "title: doc-" not in document.source


def test_recombine_documents_requires_fetched_corpus(tmp_path: Path) -> None:
    manifest = {
        "dataset_version": "test",
        "sources": [
            {
                "id": "git-md",
                "kind": "git",
                "format": "markdown",
                "repository": "https://example.com/repo.git",
                "revision": "abc",
                "include": ["**/*.md"],
            }
        ],
    }
    manifest_path = tmp_path / "parser_sources.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="fetch_parser_corpora"):
        recombine_documents(
            seed=1,
            count=1,
            manifest_path=manifest_path,
            corpus_root=tmp_path / "missing",
        )
