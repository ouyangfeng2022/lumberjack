"""Deployment-limit behavior for the public web demo (T6.2 safeguards)."""

from __future__ import annotations

import contextlib
import time
from typing import Any, cast

import anyio
import pytest
from httpx import ASGITransport, AsyncClient, Response

import lumberjack.web.routes as web_routes
from lumberjack.web import create_app
from lumberjack.web.limits import ServerLimits
from lumberjack.web.middleware import ASGIApp

SIMPLE_MD = "# Hello\n\nThis is a test paragraph.\n\n## Section\n\nAnother paragraph."


def _app(**limits: Any) -> ASGIApp:
    return create_app(serve_static=False, limits=ServerLimits(**limits))


def _post(app: ASGIApp, path: str, **kwargs: Any) -> Response:
    async def request() -> Response:
        transport = ASGITransport(app=cast(Any, app))
        async with AsyncClient(
            transport=transport, base_url="http://testserver", timeout=15.0
        ) as client:
            with anyio.fail_after(14):
                return await client.post(path, **kwargs)

    return anyio.run(request)


def _get(app: ASGIApp, path: str) -> Response:
    async def request() -> Response:
        transport = ASGITransport(app=cast(Any, app))
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
        transport = ASGITransport(app=cast(Any, app))
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


def test_chunked_body_without_content_length_is_rejected_at_the_limit() -> None:
    # No Content-Length header (chunked transfer encoding): the middleware
    # must buffer the body itself and reject mid-stream, never handing the
    # oversized payload to the application.
    app = _app(max_body_bytes=1000)
    chunks = [b"x" * 400, b"y" * 400, b"z" * 400]

    async def scenario() -> tuple[list[dict[str, Any]], int]:
        consumed = 0

        async def receive() -> dict[str, Any]:
            nonlocal consumed
            if consumed < len(chunks):
                message = {
                    "type": "http.request",
                    "body": chunks[consumed],
                    "more_body": True,
                }
                consumed += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        sent: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/lumber/api/split/text",
            "raw_path": b"/lumber/api/split/text",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        await app(scope, receive, send)
        return sent, consumed

    sent, consumed = anyio.run(scenario)
    statuses = [
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    ]
    assert statuses == [413]
    assert consumed == 3
    headers = {
        name.decode(): value.decode()
        for message in sent
        if message["type"] == "http.response.start"
        for name, value in message.get("headers", [])
    }
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"


def test_unhandled_exception_responses_still_carry_security_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json as _json

    def exploding(_chunk: Any) -> Any:
        raise RuntimeError("boom outside the pipeline try")

    monkeypatch.setattr(web_routes, "chunk_to_dict", exploding)
    app = _app()

    async def scenario() -> dict[str, Any]:
        body = _json.dumps({"text": SIMPLE_MD}).encode("utf-8")
        request_messages = [
            {"type": "http.request", "body": body, "more_body": False},
        ]

        async def receive() -> dict[str, Any]:
            if request_messages:
                return request_messages.pop(0)
            return {"type": "http.disconnect"}

        sent: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/lumber/api/split/text",
            "raw_path": b"/lumber/api/split/text",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        # ServerErrorMiddleware re-raises after sending the 500.
        with contextlib.suppress(RuntimeError):
            await app(scope, receive, send)
        start = next(m for m in sent if m["type"] == "http.response.start")
        headers = {
            name.decode(): value.decode() for name, value in start.get("headers", [])
        }
        return {"status": start["status"], "headers": headers}

    outcome = anyio.run(scenario)
    assert outcome["status"] == 500
    assert outcome["headers"]["x-content-type-options"] == "nosniff"
    assert outcome["headers"]["referrer-policy"] == "no-referrer"


def test_timed_out_worker_keeps_its_concurrency_slot_until_it_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_split = web_routes.split_source

    def slow_split(source: Any, **kwargs: Any) -> Any:
        time.sleep(0.3)
        return real_split(source, **kwargs)

    monkeypatch.setattr(web_routes, "split_source", slow_split)
    app = _app(
        split_timeout_seconds=0.05,
        max_concurrent_splits=1,
        rate_limit_requests=100,
    )
    gate = cast(Any, app).app.state.split_gate

    async def scenario() -> tuple[int, int]:
        transport = ASGITransport(app=cast(Any, app))
        async with AsyncClient(
            transport=transport, base_url="http://testserver", timeout=15.0
        ) as client:
            response = await client.post(
                "/lumber/api/split/text", json={"text": SIMPLE_MD}
            )
            assert response.status_code == 503
            held = gate.running
            deadline = time.perf_counter() + 5.0
            while gate.running and time.perf_counter() < deadline:
                await anyio.sleep(0.02)
            return held, gate.running

    held, drained = anyio.run(scenario)
    assert held == 1
    assert drained == 0


def test_multipart_file_parts_stay_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    import starlette.formparsers as formparsers

    spool_sizes: list[int] = []
    real_spooled = formparsers.SpooledTemporaryFile

    class _SpySpool(real_spooled):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            spool_sizes.append(int(kwargs.get("max_size") or 0))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", _SpySpool)
    app = _app(max_body_bytes=5 * 1024 * 1024)
    content = ("# Title\n\n" + "word " * 300_000).encode("utf-8")
    assert len(content) > 1024 * 1024  # would roll at the 1MiB default

    response = _post(
        app,
        "/lumber/api/split/file",
        files={"file": ("big.md", io.BytesIO(content), "text/markdown")},
        data={"max_tokens": "200"},
    )

    assert response.status_code == 200
    assert spool_sizes
    assert all(size >= len(content) for size in spool_sizes)


def test_non_finite_limit_values_fail_at_startup() -> None:
    for field in ("split_timeout_seconds", "rate_limit_window_seconds"):
        for bad in (float("nan"), float("inf")):
            with pytest.raises(ValueError, match=field):
                ServerLimits(**{field: bad})  # ty: ignore[invalid-argument-type]


def test_rate_limited_response_carries_retry_after() -> None:
    app = _app(rate_limit_requests=1, rate_limit_window_seconds=60)
    assert (
        _post(app, "/lumber/api/split/text", json={"text": SIMPLE_MD}).status_code
        == 200
    )
    limited = _post(app, "/lumber/api/split/text", json={"text": SIMPLE_MD})
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) == 60


def test_rate_window_eviction_does_not_reset_unrelated_clients() -> None:
    from lumberjack.web.middleware import DemoSafetyMiddleware

    middleware = DemoSafetyMiddleware.__new__(DemoSafetyMiddleware)
    middleware.limits = ServerLimits()
    middleware._windows = {f"client-{i}": (float(i), 1) for i in range(10_001)}
    middleware._windows["client-10000"] = (99999.0, 1)

    assert middleware._allow_request({"client": ("fresh", 1)})
    assert "client-10000" in middleware._windows
    assert "client-0" not in middleware._windows


def test_block_config_error_details_are_sanitized() -> None:
    app = _app()
    response = _post(
        app,
        "/lumber/api/split/text",
        json={"text": SIMPLE_MD, "block_configs": {"code_fence": {"max-tokens": -5}}},
    )
    assert response.status_code == 400
    assert "/home/" not in response.json()["detail"]
