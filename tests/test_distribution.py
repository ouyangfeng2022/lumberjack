"""Assertions for release artifacts produced by ``uv build``.

The checks are opt-in so the source test suite does not need to create package
archives.  The package workflow supplies ``LUMBERJACK_DIST_DIR=dist``.
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from email import message_from_string
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def distributions() -> tuple[Path, Path]:
    dist_dir = os.environ.get("LUMBERJACK_DIST_DIR")
    if dist_dir is None:
        pytest.skip("distribution checks require LUMBERJACK_DIST_DIR")

    directory = Path(dist_dir)
    wheel = Path(os.environ.get("LUMBERJACK_WHEEL", ""))
    sdist = Path(os.environ.get("LUMBERJACK_SDIST", ""))
    if not wheel.name:
        wheels = list(directory.glob("lumberjack_py-*.whl"))
        assert len(wheels) == 1, f"expected one wheel in {directory}, found {wheels}"
        wheel = wheels[0]
    if not sdist.name:
        sdists = list(directory.glob("lumberjack_py-*.tar.gz"))
        assert len(sdists) == 1, f"expected one sdist in {directory}, found {sdists}"
        sdist = sdists[0]
    return wheel, sdist


def test_wheel_contains_typed_package_without_web_assets(
    distributions: tuple[Path, Path],
) -> None:
    wheel, _ = distributions

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_name = next(
            name for name in names if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode("utf-8")

    assert "lumberjack/py.typed" in names
    # The Web UI's static assets are git-ignored build outputs and are
    # deliberately not bundled; deployments build them from lumberjack_webui/.
    assert not any(name.startswith("lumberjack/web/static") for name in names)
    package_metadata = message_from_string(metadata)
    extras = {
        "all",
        "code-parsing",
        "docx",
        "haystack",
        "langchain",
        "llama-index",
        "spreadsheets",
        "tokenizers",
        "toml",
        "web",
    }
    assert set(package_metadata.get_all("Provides-Extra", [])) == extras

    requirements = set(package_metadata.get_all("Requires-Dist", []))
    requirements_by_extra = {
        extra: {
            requirement.partition(";")[0].strip()
            for requirement in requirements
            if requirement.endswith(f"extra == '{extra}'")
        }
        for extra in extras
    }
    assert requirements_by_extra["tokenizers"] == {
        "cachetools>=7.1.1",
        "tiktoken>=0.9.0",
        "transformers>=4.41.0",
    }
    assert requirements_by_extra["docx"] == {"python-docx>=1.1.0"}
    assert requirements_by_extra["web"] == {
        "fastapi>=0.115.0",
        "python-multipart>=0.0.18",
        "starlette<1.0.0",
        "uvicorn>=0.34.0",
    }
    assert requirements_by_extra["langchain"] == {"langchain-core>=0.3"}
    assert requirements_by_extra["llama-index"] == {"llama-index-core>=0.12"}
    assert requirements_by_extra["haystack"] == {"haystack-ai>=2.0"}
    assert requirements_by_extra["all"] == (
        set().union(
            *(
                values
                for extra, values in requirements_by_extra.items()
                if extra != "all"
            )
        )
    )


def test_sdist_excludes_local_and_frontend_development_outputs(
    distributions: tuple[Path, Path],
) -> None:
    _, sdist = distributions

    with tarfile.open(sdist) as archive:
        names = archive.getnames()

    assert any(name.endswith("/src/lumberjack/py.typed") for name in names)
    forbidden_parts = (
        "/lumberjack_webui/",
        "/node_modules/",
        "/data/",
        "/output/",
        "/lumberjack/web/static/",
    )
    assert not any(part in name for name in names for part in forbidden_parts)
