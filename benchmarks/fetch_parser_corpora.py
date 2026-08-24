"""Fetch version-pinned external corpora used by the parser benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "datasets" / "parser_sources.json"
DEFAULT_CORPUS_ROOT = ROOT / "datasets" / "external"
DEFAULT_MAX_HTTP_BYTES = 64 * 1024 * 1024


def _safe_child(root: Path, *parts: str) -> Path:
    """Resolve a manifest path and require it to remain below its declared root."""
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValueError(f"corpus path escapes its root: {candidate}")
    return candidate


def load_sources(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list):
        raise ValueError("parser source manifest must contain a sources array")
    return manifest


def _run(*command: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def _fetch_git(source: dict[str, Any], corpus_root: Path) -> dict[str, str]:
    destination = _safe_child(corpus_root, str(source["id"]))
    repository = str(source["repository"])
    revision = str(source["revision"])
    checkout_paths = [str(path) for path in source["checkout_paths"]]

    if destination.exists():
        if not (destination / ".git").is_dir():
            raise FileExistsError(
                f"refusing to replace non-git corpus directory: {destination}"
            )
        try:
            current = _run("git", "rev-parse", "HEAD", cwd=destination)
        except subprocess.CalledProcessError:
            current = ""
        if current:
            if current != revision:
                raise RuntimeError(
                    f"{source['id']} is at {current}, expected {revision}; "
                    "move the directory aside before fetching the pinned corpus"
                )
            if _run("git", "status", "--porcelain", cwd=destination):
                raise RuntimeError(
                    f"{source['id']} has local changes; restore the pinned corpus "
                    "before benchmarking"
                )
            return {"revision": current, "path": str(destination)}
    else:
        destination.mkdir(parents=True)
        _run("git", "init", "--quiet", cwd=destination)
        _run("git", "remote", "add", "origin", repository, cwd=destination)
        _run("git", "sparse-checkout", "init", "--no-cone", cwd=destination)

    _run("git", "sparse-checkout", "set", *checkout_paths, cwd=destination)
    _run("git", "fetch", "--quiet", "--depth", "1", "origin", revision, cwd=destination)
    _run("git", "checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=destination)
    current = _run("git", "rev-parse", "HEAD", cwd=destination)
    if current != revision:
        raise RuntimeError(f"fetched {current}, expected {revision}")
    return {"revision": current, "path": str(destination)}


def _fetch_http(source: dict[str, Any], corpus_root: Path) -> dict[str, str]:
    destination = _safe_child(corpus_root, str(source["id"]))
    destination.mkdir(parents=True, exist_ok=True)
    target = _safe_child(destination, str(source["target"]))
    expected = str(source["sha256"])
    expected_size = (
        int(source["size_bytes"]) if source.get("size_bytes") is not None else None
    )
    max_bytes = expected_size or DEFAULT_MAX_HTTP_BYTES
    if max_bytes <= 0:
        raise ValueError(f"invalid download size limit for {source['id']}")

    if not target.exists():
        with urlopen(str(source["url"]), timeout=60) as response:
            payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError(f"download for {source['id']} exceeds {max_bytes} bytes")
        if expected_size is not None and len(payload) != expected_size:
            raise ValueError(
                f"size mismatch for {source['id']}: {len(payload)} != {expected_size}"
            )
        digest = hashlib.sha256(payload).hexdigest()
        if digest != expected:
            raise ValueError(
                f"SHA-256 mismatch for {source['id']}: {digest} != {expected}"
            )
        target.write_bytes(payload)

    if expected_size is not None and target.stat().st_size != expected_size:
        raise ValueError(
            f"cached corpus size mismatch for {source['id']}: "
            f"{target.stat().st_size} != {expected_size}"
        )
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != expected:
        raise ValueError(f"cached corpus SHA-256 mismatch: {target}")
    return {"sha256": digest, "path": str(target)}


def fetch_corpora(
    corpus_root: Path,
    *,
    source_ids: set[str] | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    manifest = load_sources(manifest_path)
    corpus_root.mkdir(parents=True, exist_ok=True)
    fetched: dict[str, dict[str, str]] = {}
    for source in manifest["sources"]:
        source_id = str(source["id"])
        if source_ids is not None and source_id not in source_ids:
            continue
        kind = source.get("kind")
        if kind == "git":
            fetched[source_id] = _fetch_git(source, corpus_root)
        elif kind == "commonmark-json":
            fetched[source_id] = _fetch_http(source, corpus_root)
        elif kind == "local-cases-json":
            target = _safe_child(manifest_path.parent, str(source["target"]))
            fetched[source_id] = {
                "revision": str(source["revision"]),
                "path": str(target),
            }
        else:
            raise ValueError(f"unsupported parser corpus kind: {kind!r}")

    unknown = (source_ids or set()) - fetched.keys()
    if unknown:
        raise ValueError(f"unknown parser corpus sources: {sorted(unknown)}")
    lock_path = corpus_root / "corpus-lock.json"
    existing_sources: dict[str, Any] = {}
    if lock_path.exists():
        existing_lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if existing_lock.get("dataset_version") == manifest["dataset_version"]:
            existing_sources = dict(existing_lock.get("sources") or {})
    existing_sources.update(fetched)
    lock = {
        "dataset_version": manifest["dataset_version"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": existing_sources,
    }
    lock_path.write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return lock


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch pinned parser corpora")
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Fetch only this source id; repeat for multiple sources",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    lock = fetch_corpora(
        args.corpus_root,
        source_ids=set(args.sources) if args.sources else None,
    )
    print(json.dumps(lock, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
