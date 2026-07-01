from __future__ import annotations

from pathlib import Path


def test_dockerfile_preloads_default_transformers_tokenizer() -> None:
    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")

    assert "HF_HOME=/app/.cache/huggingface" in dockerfile
    assert "AutoTokenizer.from_pretrained" in dockerfile
    assert "bert-base-uncased" in dockerfile
