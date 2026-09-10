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
            logger.warning("%s %s -> 429 (rate limit)", scope.get("method", "?"), path)
            await _send_json(
                send,
                429,
                {"detail": "rate limit exceeded; retry later"},
                extra_headers=(
                    (
                        b"retry-after",
                        str(self.limits.rate_limit_window_seconds).encode("ascii"),
                    ),
                ),
            )
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.limits.max_body_bytes:
            logger.warning(
                "%s %s -> 413 (body %d bytes)",
                scope.get("method", "?"),
                path,
                content_length,
            )
            await _send_json(
                send,
                413,
                {"detail": f"request body exceeds {self.limits.max_body_bytes} bytes"},
            )
            return

        if content_length is None:
            # Requests without a Content-Length header (e.g. chunked
            # transfer encoding) cannot be pre-checked, so the body is
            # buffered here up to the limit before the application sees any
            # of it. Oversized bodies are rejected mid-stream without ever
            # reaching the app, which keeps memory bounded by the limit.
            buffered, replays = await self._buffer_limited_body(receive, send)
            if buffered is None:
                return
            receive = replays

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

    async def _buffer_limited_body(
        self, receive: Receive, send: Send
    ) -> tuple[list[dict[str, Any]] | None, Receive]:
        """Buffer a Content-Length-less body up to the configured limit.

        Returns ``(messages, replay)`` where ``replay`` re-delivers the
        buffered messages to the application. When the body exceeds the
        limit, a 413 response is sent here and ``messages`` is ``None`` (the
        application never runs).
        """
        messages: list[dict[str, Any]] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] == "http.request":
                total += len(message.get("body", b"") or b"")
                if total > self.limits.max_body_bytes:
                    await _send_json(
                        send,
                        413,
                        {
                            "detail": (
                                "request body exceeds "
                                f"{self.limits.max_body_bytes} bytes"
                            )
                        },
                    )
                    return None, _noop_receive
                if not message.get("more_body", False):
                    break
        index = 0

        async def replay() -> dict[str, Any]:
            nonlocal index
            if index < len(messages):
                item = messages[index]
                index += 1
                return item
            return await receive()

        return messages, replay

    def _allow_request(self, scope: Scope) -> bool:
        client = scope.get("client")
        key = client[0] if client else "unknown"
        now = time.monotonic()
        window = self._windows.get(key)
        if window is None or now - window[0] >= self.limits.rate_limit_window_seconds:
            if len(self._windows) >= 10_000:
                # Evict the oldest window instead of clearing everything: a
                # full clear lets an attacker generating many client keys
                # reset everyone's (including their own) limit state.
                for oldest in sorted(self._windows, key=self._windows.__getitem__)[
                    : len(self._windows) // 2
                ]:
                    del self._windows[oldest]
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


async def _noop_receive() -> dict[str, Any]:
    return {"type": "http.disconnect"}


async def _send_json(
    send: Send,
    status: int,
    payload: dict[str, Any],
    *,
    extra_headers: tuple[tuple[bytes, bytes], ...] = (),
) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                *_SECURITY_HEADERS,
                *extra_headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


__all__ = ["DemoSafetyMiddleware"]
