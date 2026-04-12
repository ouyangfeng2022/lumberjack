"""pytest configuration for lumberjack tests."""

from __future__ import annotations

from pathlib import Path


def pytest_configure() -> None:
    """Add src/ to sys.path for pytest discovery."""
    import sys

    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
