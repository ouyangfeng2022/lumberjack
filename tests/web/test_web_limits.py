"""Deployment-limit behavior for the public web demo (T6.2 safeguards)."""

from __future__ import annotations

import time
from typing import Any

import anyio
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

import lumberjack.web.routes as web_routes
from lumberjack.web import create_app
from lumberjack.web.limits import ServerLimits

SIMPLE_MD = "# Hello\n\nThis is a test paragraph.\n\n## Section\n\nAnother paragraph."


def _app(**limits: Any) -> FastAPI:
    return create_app(serve_static=False, limits=ServerLimits(**limits))


def _post(app: FastAPI, path: str, **kwargs: Any) -> Response:
    async def request() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver", timeout=15.0
        ) as client:
            with anyio.fail_after(14):
                return await client.post(path, **kwargs)

    return anyio.run(request)


def _get(app: FastAPI, path: str) -> Response:
    async def request() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver", timeout=15.0
        ) as client:
            with anyio.fail_after(14):
                return await client.get(path)

    return anyio.run(request)


def test_health_and_version_endpoints() -> None:
    app = _app()
    for path in ("/health", "/lumber/api/health"):
        response = _get(app, path)
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert isinstance(payload["version"], str) and payload["version"]
    for path in ("/version", "/lumber/api/version"):
        response = _get(app, path)
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload["version"], str) and payload["version"]
        assert "commit" in payload


def test_responses_carry_security_headers() -> None:
    app = _app()
    response = _get(app, "/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_oversized_text_body_returns_413() -> None:
    app = _app(max_body_bytes=64)
    response = _post(
        app,
        "/lumber/api/split/text",
        json={"text": "x" * 200, "max_tokens": 100},
    )
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]


def test_oversized_file_upload_returns_413() -> None:
    app = _app(max_body_bytes=64)
    response = _post(
        app,
        "/lumber/api/split/file",
        files={"file": ("big.md", b"x" * 200, "text/markdown")},
        data={"max_tokens": "100"},
    )
    assert response.status_code == 413


def test_rate_limit_returns_429_but_health_stays_available() -> None:
    app = _app(rate_limit_requests=2, rate_limit_window_seconds=60.0)
    for _ in range(2):
        response = _post(app, "/lumber/api/split/text", json={"text": SIMPLE_MD})
        assert response.status_code == 200
    limited = _post(app, "/lumber/api/split/text", json={"text": SIMPLE_MD})
    assert limited.status_code == 429
    assert "rate limit" in limited.json()["detail"]
    assert _get(app, "/health").status_code == 200


def test_split_timeout_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_split = web_routes.split_source

    def slow_split(source: Any, **kwargs: Any) -> Any:
        time.sleep(0.5)
        return real_split(source, **kwargs)

    monkeypatch.setattr(web_routes, "split_source", slow_split)
    app = _app(split_timeout_seconds=0.05)
    response = _post(app, "/lumber/api/split/text", json={"text": SIMPLE_MD})
    assert response.status_code == 503
    assert "time budget" in response.json()["detail"]


def test_concurrent_splits_are_serialized_by_the_concurrency_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_split = web_routes.split_source

    def slow_split(source: Any, **kwargs: Any) -> Any:
        time.sleep(0.25)
        return real_split(source, **kwargs)

    monkeypatch.setattr(web_routes, "split_source", slow_split)
    app = _app(max_concurrent_splits=1, rate_limit_requests=100)

    async def run_two() -> list[Response]:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver", timeout=15.0
        ) as client:

            async def one() -> Response:
                return await client.post(
                    "/lumber/api/split/text", json={"text": SIMPLE_MD}
                )

            results: list[Response] = []
            async with anyio.create_task_group() as task_group:
                for _ in range(2):
                    task_group.start_soon(_collect, one, results)
            return results

    async def _collect(call: Any, results: list[Response]) -> None:
        results.append(await call())

    started = time.perf_counter()
    responses = anyio.run(run_two)
    elapsed = time.perf_counter() - started
    assert [response.status_code for response in responses] == [200, 200]
    assert elapsed >= 0.4


def test_error_details_do_not_leak_local_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_split(source: Any, **_kwargs: Any) -> Any:
        raise ValueError(f"cannot open /home/elery/secret/{source[:6]}.md")

    monkeypatch.setattr(web_routes, "split_source", failing_split)
    app = _app()
    response = _post(app, "/lumber/api/split/text", json={"text": SIMPLE_MD})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "/home/elery" not in detail
    assert "<path>" in detail


def test_limit_environment_variables_are_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LUMBERJACK_WEB_MAX_BODY_BYTES", "2048")
    monkeypatch.setenv("LUMBERJACK_WEB_RATE_LIMIT_REQUESTS", "5")
    limits = ServerLimits.from_env()
    assert limits.max_body_bytes == 2048
    assert limits.rate_limit_requests == 5
    assert limits.max_concurrent_splits == ServerLimits().max_concurrent_splits


def test_invalid_limit_environment_variable_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LUMBERJACK_WEB_MAX_CONCURRENT_SPLITS", "zero")
    with pytest.raises(ValueError, match="LUMBERJACK_WEB_MAX_CONCURRENT_SPLITS"):
        ServerLimits.from_env()
