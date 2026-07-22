from __future__ import annotations

import io
from typing import Any

import anyio
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from lumberjack.web import create_app


class ASGITestClient:
    """Small synchronous facade over HTTPX's in-process ASGI transport.

    Starlette's synchronous ``TestClient`` uses an AnyIO blocking portal and can
    deadlock in otherwise supported local environments. Exercising the ASGI
    app directly keeps these tests on a single event loop while preserving the
    existing request/response assertions.
    """

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def post(self, path: str, **kwargs: Any) -> Response:
        async def request() -> Response:
            transport = ASGITransport(app=self.app)
            async with AsyncClient(
                transport=transport,
                base_url="http://testserver",
                timeout=10.0,
            ) as client:
                with anyio.fail_after(10):
                    return await client.post(path, **kwargs)

        return anyio.run(request)


@pytest.fixture
def client() -> ASGITestClient:
    return ASGITestClient(create_app(serve_static=False))


SIMPLE_MD = "# Hello\n\nThis is a test paragraph.\n\n## Section\n\nAnother paragraph."


def test_split_with_text(client: ASGITestClient) -> None:
    response = client.post(
        "/lumber/api/split/text",
        json={"text": SIMPLE_MD, "max_tokens": 500},
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


def test_split_text_accepts_html_format(client: ASGITestClient) -> None:
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": "<html><body><h1>Guide</h1><p>Intro</p></body></html>",
            "input_format": "html",
            "max_tokens": 500,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document"] == "Guide"
    assert body["chunks"][0]["body"] == "# Guide\n\nIntro"


def test_split_with_file(client: ASGITestClient) -> None:
    md_file = io.BytesIO(SIMPLE_MD.encode("utf-8"))
    response = client.post(
        "/lumber/api/split/file",
        files={"file": ("guide.md", md_file, "text/markdown")},
        data={"max_tokens": "500"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document"] == "guide.md"
    assert body["chunk_count"] >= 1


def test_split_text_accepts_render_headings_false(client: ASGITestClient) -> None:
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": "# Parent\n\nIntro.",
            "max_tokens": 500,
            "render_headings": False,
        },
    )

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["headings"] == []
    assert chunk["body"] == "# Parent\n\nIntro."


def test_split_file_accepts_render_headings_false(client: ASGITestClient) -> None:
    md_file = io.BytesIO(b"# Parent\n\nIntro.")
    response = client.post(
        "/lumber/api/split/file",
        files={"file": ("guide.md", md_file, "text/markdown")},
        data={"max_tokens": "500", "render_headings": "false"},
    )

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["headings"] == []
    assert chunk["body"] == "# Parent\n\nIntro."


def test_split_text_accepts_max_heading_level(client: ASGITestClient) -> None:
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": "# Parent\n\n## Child\n\n### Detail\n\nBody.",
            "max_tokens": 500,
            "max_heading_level": 2,
        },
    )

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["headings"] == [[1, "Parent"]]
    assert chunk["section_level"] == 2
    assert "### Detail" in chunk["body"]


def test_split_file_accepts_max_heading_level(client: ASGITestClient) -> None:
    md_file = io.BytesIO(b"# Parent\n\n## Child\n\n### Detail\n\nBody.")
    response = client.post(
        "/lumber/api/split/file",
        files={"file": ("guide.md", md_file, "text/markdown")},
        data={"max_tokens": "500", "max_heading_level": "2"},
    )

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["headings"] == [[1, "Parent"]]
    assert chunk["section_level"] == 2
    assert "### Detail" in chunk["body"]


def test_split_with_html_file_auto_detects_format(client: ASGITestClient) -> None:
    html_file = io.BytesIO(b"<html><body><h1>Guide</h1><p>Intro</p></body></html>")
    response = client.post(
        "/lumber/api/split/file",
        files={"file": ("guide.html", html_file, "text/html")},
        data={"max_tokens": "500"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document"] == "guide.html"
    assert body["chunks"][0]["body"] == "# Guide\n\nIntro"


def test_split_no_input(client: ASGITestClient) -> None:
    response = client.post("/lumber/api/split/text", json={})
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


def test_split_with_options(client: ASGITestClient) -> None:
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": SIMPLE_MD,
            "max_tokens": 100,
            "ideal_max_tokens_ratio": 0.8,
            "merge_below_ratio": 0.0,
            "block_configs": {"paragraph": {"isolated": False}},
            "tokenizer": "tiktoken",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["chunk_count"] >= 1


def test_split_ignores_legacy_render_common_headings_form_field(
    client: ASGITestClient,
) -> None:
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": "# Parent\n\n## Child\n\nChild body.",
            "max_tokens": 500,
            "render_common_headings": False,
        },
    )

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["headings"] == [[1, "Parent"]]
    assert chunk["body"] == "# Parent\n\n## Child\n\nChild body."


def test_unprefixed_api_path_is_not_registered(client: ASGITestClient) -> None:
    response = client.post("/api/split/text", json={"text": SIMPLE_MD})
    # 405 when the static SPA catch-all is mounted, 404 in API-only mode.
    # Both confirm the route itself is not registered as a valid endpoint.
    assert response.status_code in (404, 405)


def test_legacy_combined_split_path_is_not_registered(client: ASGITestClient) -> None:
    response = client.post("/lumber/api/split", data={"text": SIMPLE_MD})
    # 405 when the static SPA catch-all is mounted, 404 in API-only mode.
    # Both confirm the route itself is not registered as a valid endpoint.
    assert response.status_code in (404, 405)


def test_split_with_block_configs(client: ASGITestClient) -> None:
    md = "# Doc\n\nIntro.\n\n| A |\n|---|\n| 1 |\n\nOutro."
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": md,
            "max_tokens": 500,
            "block_configs": {"table": {"isolated": True}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    table_chunks = [c for c in body["chunks"] if c["chunk_type"] == "table"]
    assert len(table_chunks) == 1
    assert "| A |" in table_chunks[0]["body"]
    assert "Intro." not in table_chunks[0]["body"]


def test_split_rejects_invalid_block_params_field(client: ASGITestClient) -> None:
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": "# Doc\n\n| A |\n|---|\n| 1 |",
            "block_configs": {
                "table": {"isolate": True, "split": True, "max_tokens": 500}
            },
        },
    )

    assert response.status_code == 400
    assert "isolated" in response.json()["detail"]


def test_split_with_table_block_params(client: ASGITestClient) -> None:
    md = """| Name | Value |
| ---- | ----- |
| Alpha | 100 |
| Beta | 200 |
| Gamma | 300 |
| Delta | 400 |
"""
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": md,
            "max_tokens": 5,
            "ideal_max_tokens_ratio": 1,
            "merge_below_ratio": 0.0,
            "block_configs": {"table": {"repeat_header": False}},
        },
    )

    assert response.status_code == 200
    chunks = response.json()["chunks"]
    assert len(chunks) == 4
    assert "| Name | Value |" in chunks[0]["body"]
    assert all("| Name | Value |" not in chunk["body"] for chunk in chunks[1:])


def test_split_rejects_unknown_table_params_field(client: ASGITestClient) -> None:
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": "| A |\n|---|\n| 1 |",
            "block_configs": {"table": {"repeat_headers": False}},
        },
    )

    assert response.status_code == 400
    assert "repeat_header" in response.json()["detail"]


def test_split_rejects_table_specific_field_for_non_table_kind(
    client: ASGITestClient,
) -> None:
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": "Paragraph.",
            "block_configs": {"paragraph": {"repeat_header": False}},
        },
    )

    assert response.status_code == 400
    assert "repeat_header" in response.json()["detail"]


def test_split_block_configs_default_applies_when_field_not_sent(
    client: ASGITestClient,
) -> None:
    """Default block_configs (all DEFAULT, allow merge) applies when field is absent."""
    md = "# Doc\n\nIntro.\n\n| A |\n|---|\n| 1 |\n\nOutro."
    response = client.post(
        "/lumber/api/split/text",
        json={
            "text": md,
            "max_tokens": 500,
        },
    )
    assert response.status_code == 200
    body = response.json()
    # With default DEFAULT policy, table can merge with adjacent content
    # So all content should be in one chunk
    assert body["chunk_count"] == 1


def test_split_text_with_approx(client: ASGITestClient) -> None:
    """The /split/text endpoint works with the approx (exact) tokenizer."""
    payload = {
        "text": "# T\n\nbody text here\n",
        "input_format": "markdown",
        "tokenizer": "approx",
    }
    response = client.post("/lumber/api/split/text", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["chunk_count"] >= 1
    chunk = data["chunks"][0]
    assert chunk["token_count"] == len(chunk["body"].encode("utf-8")) // 3


def test_split_text_with_tiktoken(client: ASGITestClient) -> None:
    payload = {
        "text": "# T\n\nThe quick brown fox jumps over the lazy dog "
        "repeatedly every single day without fail.\n",
        "input_format": "markdown",
        "tokenizer": "tiktoken",
    }
    response = client.post("/lumber/api/split/text", json=payload)
    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    # tiktoken reports a full cached recount; on typical English text it maps
    # to roughly 4 bytes per token and so must be strictly less than the
    # bytes//3 approx estimate, and > 0.
    assert chunk["token_count"] > 0
    assert chunk["token_count"] < len(chunk["body"].encode("utf-8")) // 3


def test_split_file_with_approx(client: ASGITestClient) -> None:
    response = client.post(
        "/lumber/api/split/file",
        data={
            "input_format": "markdown",
            "tokenizer": "approx",
        },
        files={"file": ("doc.md", io.BytesIO(b"# T\n\nbody\n"), "text/markdown")},
    )
    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["token_count"] == len(chunk["body"].encode("utf-8")) // 3
