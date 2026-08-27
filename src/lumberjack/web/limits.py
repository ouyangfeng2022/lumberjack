"""Deployment limits for the public web demo.

The split endpoints accept untrusted input, so a public deployment must bound
request size, concurrency, request rate, and split duration. Values come from
environment variables so operators can tune them without code changes; the
defaults are conservative for a small demo deployment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_MAX_BODY_BYTES = 5 * 1024 * 1024
_DEFAULT_MAX_CONCURRENT_SPLITS = 2
_DEFAULT_SPLIT_TIMEOUT_SECONDS = 30.0
_DEFAULT_RATE_LIMIT_REQUESTS = 60
_DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class ServerLimits:
    """Resource limits enforced by the web layer."""

    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES
    max_concurrent_splits: int = _DEFAULT_MAX_CONCURRENT_SPLITS
    split_timeout_seconds: float = _DEFAULT_SPLIT_TIMEOUT_SECONDS
    rate_limit_requests: int = _DEFAULT_RATE_LIMIT_REQUESTS
    rate_limit_window_seconds: float = _DEFAULT_RATE_LIMIT_WINDOW_SECONDS

    def __post_init__(self) -> None:
        if self.max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")
        if self.max_concurrent_splits <= 0:
            raise ValueError("max_concurrent_splits must be positive")
        if self.split_timeout_seconds <= 0:
            raise ValueError("split_timeout_seconds must be positive")
        if self.rate_limit_requests <= 0:
            raise ValueError("rate_limit_requests must be positive")
        if self.rate_limit_window_seconds <= 0:
            raise ValueError("rate_limit_window_seconds must be positive")

    @classmethod
    def from_env(cls) -> ServerLimits:
        """Read limits from ``LUMBERJACK_WEB_*`` environment variables.

        Unset variables fall back to the defaults. Invalid values raise
        ``ValueError`` instead of being silently ignored, so a misconfigured
        deployment fails loudly at startup.
        """
        return cls(
            max_body_bytes=_int_env(
                "LUMBERJACK_WEB_MAX_BODY_BYTES", _DEFAULT_MAX_BODY_BYTES
            ),
            max_concurrent_splits=_int_env(
                "LUMBERJACK_WEB_MAX_CONCURRENT_SPLITS", _DEFAULT_MAX_CONCURRENT_SPLITS
            ),
            split_timeout_seconds=_float_env(
                "LUMBERJACK_WEB_SPLIT_TIMEOUT_SECONDS", _DEFAULT_SPLIT_TIMEOUT_SECONDS
            ),
            rate_limit_requests=_int_env(
                "LUMBERJACK_WEB_RATE_LIMIT_REQUESTS", _DEFAULT_RATE_LIMIT_REQUESTS
            ),
            rate_limit_window_seconds=_float_env(
                "LUMBERJACK_WEB_RATE_LIMIT_WINDOW_SECONDS",
                _DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
            ),
        )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from error


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a number, got {raw!r}") from error


def package_version() -> str:
    """Return the installed distribution version, or a dev placeholder."""
    from importlib import metadata

    try:
        return metadata.version("lumberjack-py")
    except metadata.PackageNotFoundError:
        return "0.0.0.dev0"


def build_commit() -> str | None:
    """Return the commit injected at image build time, if any."""
    value = os.environ.get("LUMBERJACK_BUILD_COMMIT")
    return value if value else None


__all__ = ["ServerLimits", "build_commit", "package_version"]
