from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from lumberjack.web import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


SIMPLE_MD = "# Hello\n\nThis is a test paragraph.\n\n## Section\n\nAnother paragraph."


def test_split_with_text(client: TestClient) -> None:
    response = client.post(
        "/lumber/api/split",
        data={"text": SIMPLE_MD, "max_tokens": "500"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document"] == "Hello"
    assert body["chunk_count"] >= 1
    assert len(body["chunks"]) == body["chunk_count"]
    chunk = body["chunks"][0]
    assert "chunk_id" in chunk
    assert "body" in chunk
    assert "token_count" in chunk
    assert "estimated_token_count" in chunk
    assert "headings" in chunk


def test_split_with_file(client: TestClient) -> None:
    md_file = io.BytesIO(SIMPLE_MD.encode("utf-8"))
    response = client.post(
        "/lumber/api/split",
        files={"file": ("guide.md", md_file, "text/markdown")},
        data={"max_tokens": "500"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document"] == "guide.md"
    assert body["chunk_count"] >= 1


def test_split_no_input(client: TestClient) -> None:
    response = client.post("/lumber/api/split")
    assert response.status_code == 400
    body = response.json()
    assert "detail" in body


def test_split_with_options(client: TestClient) -> None:
    response = client.post(
        "/lumber/api/split",
        data={
            "text": SIMPLE_MD,
            "max_tokens": "100",
            "merge_below_tokens": "10",
            "overlap_tokens": "5",
            "retain_headings": "true",
            "merge_small_chunks": "false",
            "split_oversized_blocks": "paragraph",
            "tokenizer": "simple",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["chunk_count"] >= 1


def test_split_can_disable_setext_headings(client: TestClient) -> None:
    response = client.post(
        "/lumber/api/split",
        data={
            "text": "Title\n=====\n\nbody",
            "max_tokens": "500",
            "retain_headings": "false",
            "disable_lheading": "true",
        },
    )

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["body"] == "Title\n=====\n\nbody"
    assert chunk["headings"] == []


def test_pipeline_uses_lumber_prefix(client: TestClient) -> None:
    response = client.post(
        "/lumber/api/pipeline",
        data={"text": SIMPLE_MD, "max_tokens": "500"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stage_5_chunks"]["chunk_count"] >= 1


def test_pipeline_split_entries_expose_only_rendering_inputs(client: TestClient) -> None:
    response = client.post(
        "/lumber/api/pipeline",
        data={"text": SIMPLE_MD, "max_tokens": "500"},
    )

    assert response.status_code == 200
    entry = response.json()["stage_4_split"]["entries"][0]
    assert set(entry) == {
        "headings",
        "body",
        "start_line",
        "end_line",
        "body_token_count",
    }


def test_pipeline_ast_does_not_expose_splitter_token_counts(client: TestClient) -> None:
    response = client.post(
        "/lumber/api/pipeline",
        data={"text": SIMPLE_MD, "max_tokens": "500"},
    )

    assert response.status_code == 200
    root = response.json()["stage_3_ast"]["root"]
    assert "title_token_count" not in root
    assert "body_token_count" not in root
    assert "subtree_token_count" not in root


def test_unprefixed_api_path_is_not_registered(client: TestClient) -> None:
    response = client.post("/api/split", data={"text": SIMPLE_MD})
    assert response.status_code == 405
