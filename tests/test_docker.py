from __future__ import annotations

from pathlib import Path


def test_dockerfile_preloads_default_transformers_tokenizer() -> None:
    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")

    assert "HF_HOME=/app/.cache/huggingface" in dockerfile
    assert "AutoTokenizer.from_pretrained" in dockerfile
    assert "bert-base-uncased" in dockerfile


def test_dockerfile_installs_non_editable_wheel() -> None:
    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")

    # The production image must contain an immutable installed package rather
    # than an editable link into a mounted source tree.
    assert "uv build --wheel" in dockerfile
    assert "uv pip install --python /app/.venv/bin/python /app/dist/*.whl" in dockerfile
    assert "uv sync --frozen --no-dev --extra all\n" not in dockerfile
    # The frontend assets are copied into the installed package because the
    # wheel itself excludes the gitignored web/static directory.
    assert 'pathlib.Path(lumberjack.__file__).parent / "web" / "static"' in dockerfile
    assert "cp -r /app/frontend-dist/." in dockerfile


def test_dockerfile_exposes_build_commit_and_has_no_build_tools() -> None:
    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")

    assert "ARG COMMIT=" in dockerfile
    assert "LUMBERJACK_BUILD_COMMIT" in dockerfile
    # No uv binary and no source tree in the runtime stage.
    assert "COPY --from=ghcr.io/astral-sh/uv:latest" not in dockerfile
    assert "COPY src/ ./src/" not in dockerfile.split("Stage 3")[-1]


def test_compose_uses_health_endpoint_and_commit_arg() -> None:
    compose = Path("docker/docker-compose.yml").read_text(encoding="utf-8")

    assert "COMMIT: ${COMMIT:-}" in compose
    assert "http://localhost:9612/health" in compose
    # No source bind mounts: the image ships an installed package.
    assert "volumes:" not in compose
