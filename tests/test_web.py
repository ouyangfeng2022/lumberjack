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
            "merge_small_chunks": "false",
            "split_oversized_blocks": "paragraph",
            "tokenizer": "simple",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["chunk_count"] >= 1


def test_split_accepts_heading_splitter_with_recursive_split(
    client: TestClient,
) -> None:
    response = client.post(
        "/lumber/api/split",
        data={
            "text": "# Parent\n\nParent intro.\n\n## Child\n\nChild body.",
            "max_tokens": "500",
            "splitter": "section",
            "recursive_split": "true",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [chunk["headings"] for chunk in body["chunks"]] == [
        [[1, "Parent"]],
        [[1, "Parent"], [2, "Child"]],
    ]


def test_split_can_disable_setext_headings(client: TestClient) -> None:
    response = client.post(
        "/lumber/api/split",
        data={
            "text": "Title\n=====\n\nbody",
            "max_tokens": "500",
            "disable_lheading": "true",
        },
    )

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["body"] == "Title\n=====\n\nbody"
    assert chunk["headings"] == []


def test_split_ignores_legacy_render_common_headings_form_field(
    client: TestClient,
) -> None:
    response = client.post(
        "/lumber/api/split",
        data={
            "text": "# Parent\n\n## Child\n\nChild body.",
            "max_tokens": "500",
            "render_common_headings": "false",
        },
    )

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["headings"] == [[1, "Parent"], [2, "Child"]]
    assert chunk["body"] == "# Parent\n\n## Child\n\nChild body."


def test_unprefixed_api_path_is_not_registered(client: TestClient) -> None:
    response = client.post("/api/split", data={"text": SIMPLE_MD})
    assert response.status_code == 405


def test_split_with_standalone_blocks(client: TestClient) -> None:
    md = "# Doc\n\nIntro.\n\n| A |\n|---|\n| 1 |\n\nOutro."
    response = client.post(
        "/lumber/api/split",
        data={
            "text": md,
            "max_tokens": "500",
            "standalone_blocks": "table",
        },
    )
    assert response.status_code == 200
    body = response.json()
    table_chunks = [c for c in body["chunks"] if c["chunk_type"] == "table"]
    assert len(table_chunks) == 1
    assert "| A |" in table_chunks[0]["body"]
    assert "Intro." not in table_chunks[0]["body"]


def test_split_standalone_blocks_default_applies_when_field_not_sent(
    client: TestClient,
) -> None:
    """Default standalone_blocks (table, code_block, code_fence) applies when field is absent."""
    md = "# Doc\n\nIntro.\n\n| A |\n|---|\n| 1 |\n\nOutro."
    response = client.post(
        "/lumber/api/split",
        data={
            "text": md,
            "max_tokens": "500",
        },
    )
    assert response.status_code == 200
    body = response.json()
    table_chunks = [c for c in body["chunks"] if c["chunk_type"] == "table"]
    assert len(table_chunks) == 1
    assert "Intro." not in table_chunks[0]["body"]
