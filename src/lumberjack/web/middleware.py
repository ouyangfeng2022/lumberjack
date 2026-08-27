"""ASGI middleware enforcing the public-demo safety limits.

The middleware runs before request parsing so oversized payloads are rejected
without being buffered, applies a fixed-window per-client rate limit, adds
basic security headers, and logs every request with method, path, status, and
duration. It never logs request or response bodies, so document content stays
out of the logs (see the privacy notes in the web API documentation).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .limits import ServerLimits

logger = logging.getLogger("lumberjack.web")

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
)


class DemoSafetyMiddleware:
    """Body-size pre-check, per-client rate limit, and request logging."""

    def __init__(self, app: ASGIApp, limits: ServerLimits) -> None:
        self.app = app
        self.limits = limits
        # client key -> (window start monotonic time, request count)
        self._windows: dict[str, tuple[float, int]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        is_api_request = path.startswith("/lumber/api/") and path not in (
            "/lumber/api/health",
            "/lumber/api/version",
        )

        if is_api_request and not self._allow_request(scope):
            await _send_json(send, 429, {"detail": "rate limit exceeded; retry later"})
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.limits.max_body_bytes:
            await _send_json(
                send,
                413,
                {"detail": f"request body exceeds {self.limits.max_body_bytes} bytes"},
            )
            return

        started = time.perf_counter()
        status_code = 0

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.extend(_SECURITY_HEADERS)
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            method = scope.get("method", "?")
            if is_api_request:
                if status_code >= 500:
                    logger.error(
                        "%s %s -> %d (%.1fms)", method, path, status_code, duration_ms
                    )
                else:
                    logger.info(
                        "%s %s -> %d (%.1fms)", method, path, status_code, duration_ms
                    )
            else:
                logger.debug(
                    "%s %s -> %d (%.1fms)", method, path, status_code, duration_ms
                )

    def _allow_request(self, scope: Scope) -> bool:
        client = scope.get("client")
        key = client[0] if client else "unknown"
        now = time.monotonic()
        window = self._windows.get(key)
        if window is None or now - window[0] >= self.limits.rate_limit_window_seconds:
            if len(self._windows) >= 10_000:
                self._windows.clear()
            self._windows[key] = (now, 1)
            return True
        start, count = window
        if count >= self.limits.rate_limit_requests:
            return False
        self._windows[key] = (start, count + 1)
        return True


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _send_json(send: Send, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                *_SECURITY_HEADERS,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


__all__ = ["DemoSafetyMiddleware"]
