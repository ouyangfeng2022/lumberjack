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
    assert body["document"] == "document.md"
    assert body["chunk_count"] >= 1
    assert len(body["chunks"]) == body["chunk_count"]
    chunk = body["chunks"][0]
    assert "chunk_id" in chunk
    assert "body" in chunk
    assert "token_count" in chunk
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
    assert response.status_code == 200
    body = response.json()
    assert "error" in body


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


def test_pipeline_uses_lumber_prefix(client: TestClient) -> None:
    response = client.post(
        "/lumber/api/pipeline",
        data={"text": SIMPLE_MD, "max_tokens": "500"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stage_5_chunks"]["chunk_count"] >= 1


def test_unprefixed_api_path_is_not_registered(client: TestClient) -> None:
    response = client.post("/api/split", data={"text": SIMPLE_MD})
    assert response.status_code == 405
