"""Seeded random Markdown corpora for large-scale splitter benchmarking.

Two independent dataset builders feed ``splitter_random_run``:

1. Synthetic shape generators — six structural profiles (deep heading trees,
   wide sibling fans, budget-pressure sections, oversized protected blocks,
   tiny/empty sections, degenerate edge documents). Every document carries
   sentinel oracles: body sentinels must survive in some chunk, and code
   sentinels must appear in exactly one chunk (no loss or duplication).
2. Real-corpus recombination — section spans sampled from the pinned external
   Markdown corpora (Kubernetes docs, CommonMark spec cases, local element
   cases) stitched into new documents. Fidelity is checked downstream with
   word-level recall against the parsed tree's own text, so no generator
   truth is needed.

Both builders are pure functions of the seed: every document uses its own
``random.Random`` derived from ``f"{seed}:{kind}:{index}"``.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from benchmarks.parser_run import (
    _commonmark_documents,
    _git_documents,
    _load_manifest,
    _local_case_documents,
)
from benchmarks.random_corpus import _WORDS, _Oracle
from lumberjack.tokenizer import ApproxByteTokenizer

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "datasets" / "parser_sources.json"
DEFAULT_CORPUS_ROOT = ROOT / "datasets" / "external"

#: Upper bound for one recombined document; keeps exact-mode runs bounded.
RECOMBINED_MAX_BYTES = 60_000

_SIZE_TOKENIZER = ApproxByteTokenizer()


def _size_tokens(text: str) -> int:
    return _SIZE_TOKENIZER.count(text)


@dataclass(frozen=True, slots=True)
class RandomSplitDocument:
    """One generated/recombined document plus the oracles splitters must satisfy."""

    dataset: str
    document_id: str
    shape: str
    source: str
    required_content: tuple[str, ...] = ()
    protected_content: tuple[str, ...] = ()
    min_word_recall: float = 0.99
    profile: dict[str, Any] = field(default_factory=dict)


class _Sentinels:
    """Per-document sentinel namespaces with a single shared RNG stream."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.body = _Oracle(rng, "LJS_B_")
        self.code = _Oracle(rng, "LJS_C_")


_CODE_LANGUAGES = ("python", "bash", "json", "typescript", "rust", "")


def _heading_title(sent: _Sentinels) -> str:
    return " ".join(sent.body.words(2, 5))


def _styled_sentence(sent: _Sentinels) -> str:
    """One sentence with occasional inline markup (surface syntax preserved)."""
    text = sent.body.sentence()
    choice = sent.rng.random()
    if choice < 0.08:
        return f"**{text}**"
    if choice < 0.14:
        return f"*{text}*"
    if choice < 0.19:
        return f"`{sent.rng.choice(_WORDS)}` then {text}"
    if choice < 0.24:
        return f"[{text}](https://example.com/{sent.rng.randrange(1000)})"
    return text


def _paragraph(sent: _Sentinels, target_tokens: int, *, anchor: bool = True) -> str:
    pieces: list[str] = []
    if anchor:
        pieces.append(f"{sent.body.sentinel()} {sent.body.sentence()}.")
    while _size_tokens(" ".join(pieces)) < target_tokens:
        pieces.append(f"{_styled_sentence(sent)}.")
    return " ".join(pieces)


def _one_line_body(sent: _Sentinels) -> str:
    return f"{sent.body.sentinel()} {sent.body.sentence()}."


def _code_fence(sent: _Sentinels, target_tokens: int) -> str:
    language = sent.rng.choice(_CODE_LANGUAGES)
    lines = [f"# {sent.code.sentinel()} {sent.code.sentence()}"]
    while _size_tokens("\n".join(lines)) < target_tokens:
        lines.append(f"# {sent.code.sentence()}")
    return f"```{language}\n" + "\n".join(lines) + "\n```"


def _table(sent: _Sentinels, *, target_tokens: int | None = None) -> str:
    columns = sent.rng.randint(2, 5)
    header = [f"col{index}" for index in range(1, columns + 1)]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * columns) + " |",
        "| "
        + " | ".join(
            [
                sent.body.sentinel(),
                *(" ".join(sent.body.words(1, 3)) for _ in range(columns - 1)),
            ]
        )
        + " |",
    ]
    minimum_rows = sent.rng.randint(3, 8) if target_tokens is None else 3
    data_rows = 1
    while data_rows < minimum_rows or (
        target_tokens is not None and _size_tokens("\n".join(lines)) < target_tokens
    ):
        cells = (" ".join(sent.body.words(1, 4)) for _ in range(columns))
        lines.append("| " + " | ".join(cells) + " |")
        data_rows += 1
    return "\n".join(lines)


def _list(sent: _Sentinels, *, depth: int = 1, items: int | None = None) -> str:
    count = items if items is not None else sent.rng.randint(3, 7)
    lines: list[str] = []
    for index in range(count):
        marker = "- " if sent.rng.random() < 0.7 else f"{index + 1}. "
        text = _one_line_body(sent) if index == 0 else f"{sent.body.sentence()}."
        lines.append(f"{marker}{text}")
        if depth > 1 and sent.rng.random() < 0.35 and index + 1 < count:
            lines.extend(
                f"  {line}" for line in _list(sent, depth=depth - 1).splitlines()
            )
    return "\n".join(lines)


def _blockquote(sent: _Sentinels) -> str:
    lines = ["> " + _one_line_body(sent)]
    for _ in range(sent.rng.randint(0, 2)):
        lines.append("> " + sent.body.sentence() + ".")
    if sent.rng.random() < 0.3:
        lines.append("> > " + sent.body.sentence() + ".")
    return "\n".join(lines)


def _math_block(sent: _Sentinels) -> str:
    return "\\[\na_{" + str(sent.rng.randrange(100)) + "}^2 + b = c\n\\]"


def _giant_word_line(target_tokens: int) -> str:
    """A single space-free line: forces the word -> hard-split fallback."""
    return "q" * max(8, target_tokens * 3)


def _ensure_body_anchor(blocks: list[str], sent: _Sentinels, budget: int) -> None:
    if sent.body.sentinels():
        return
    blocks.append(_paragraph(sent, max(12, budget // 10)))


def _document(
    shape: str,
    blocks: list[str],
    sent: _Sentinels,
    *,
    variant: str | None = None,
) -> RandomSplitDocument:
    source = "\n\n".join(blocks) + "\n"
    profile = _profile(source)
    if variant is not None:
        profile["variant"] = variant
    return RandomSplitDocument(
        dataset="",
        document_id="",
        shape=shape,
        source=source,
        required_content=tuple(sent.body.sentinels()),
        protected_content=tuple(sent.code.sentinels()),
        profile=profile,
    )


def _generate_deep_tree(rng: random.Random, budget: int) -> RandomSplitDocument:
    sent = _Sentinels(rng)
    blocks: list[str] = []
    max_level = rng.choice((4, 5, 6))

    def walk(level: int) -> None:
        blocks.append(f"{'#' * level} {_heading_title(sent)}")
        for _ in range(rng.randint(0, 2)):
            blocks.append(
                _paragraph(sent, max(12, int(budget * rng.uniform(0.05, 0.2))))
            )
        if level < max_level:
            # A strict +1 spine down to level 4 guarantees nesting depth; only
            # deeper levels may skip heading numbers.
            if level < 4:
                next_level = level + 1
            else:
                next_level = min(6, level + rng.choice((1, 2)))
            for _ in range(2 if rng.random() < 0.2 else 1):
                walk(next_level)

    walk(1)
    _ensure_body_anchor(blocks, sent, budget)
    return _document("deep-tree", blocks, sent)


def _generate_wide_flat(rng: random.Random, budget: int) -> RandomSplitDocument:
    sent = _Sentinels(rng)
    blocks: list[str] = [f"# {_heading_title(sent)}"]
    duplicate_title = _heading_title(sent)
    for index in range(rng.randint(8, 20)):
        title = (
            duplicate_title
            if index > 0 and rng.random() < 0.15
            else _heading_title(sent)
        )
        blocks.append(f"## {title}")
        choice = rng.random()
        if choice < 0.15:
            continue
        if choice < 0.75:
            for _ in range(rng.randint(1, 3)):
                blocks.append(
                    _paragraph(sent, max(12, int(budget * rng.uniform(0.05, 0.3))))
                )
        elif choice < 0.9:
            blocks.append(_list(sent, depth=2))
        else:
            blocks.append(
                _table(sent, target_tokens=int(budget * rng.uniform(0.1, 0.4)))
            )
        if rng.random() < 0.12:
            blocks.append(f"### {_heading_title(sent)}")
            blocks.append(_paragraph(sent, max(12, budget // 10)))
    _ensure_body_anchor(blocks, sent, budget)
    return _document("wide-flat", blocks, sent)


def _generate_long_sections(rng: random.Random, budget: int) -> RandomSplitDocument:
    sent = _Sentinels(rng)
    blocks: list[str] = []
    for index in range(rng.randint(2, 4)):
        level = 1 if index == 0 else rng.choice((1, 2))
        blocks.append(f"{'#' * level} {_heading_title(sent)}")
        for position in range(rng.randint(6, 14)):
            if position > 0 and rng.random() < 0.15:
                blocks.append(_paragraph(sent, int(budget * rng.uniform(1.2, 1.8))))
            else:
                blocks.append(_paragraph(sent, int(budget * rng.uniform(0.2, 0.8))))
        if rng.random() < 0.3:
            blocks.append(_blockquote(sent))
        if rng.random() < 0.3:
            blocks.append(_math_block(sent))
    _ensure_body_anchor(blocks, sent, budget)
    return _document("long-sections", blocks, sent)


def _generate_oversized_blocks(rng: random.Random, budget: int) -> RandomSplitDocument:
    sent = _Sentinels(rng)
    blocks: list[str] = [f"# {_heading_title(sent)}"]
    for _ in range(rng.randint(3, 6)):
        blocks.append(f"## {_heading_title(sent)}")
        blocks.append(_paragraph(sent, int(budget * rng.uniform(0.1, 0.4))))
        choice = rng.random()
        if choice < 0.45:
            blocks.append(_code_fence(sent, int(budget * rng.uniform(1.2, 2.5))))
        elif choice < 0.7:
            blocks.append(
                _table(sent, target_tokens=int(budget * rng.uniform(1.2, 2.0)))
            )
        else:
            blocks.append(_giant_word_line(int(budget * rng.uniform(1.2, 2.0))))
        blocks.append(
            _paragraph(sent, int(budget * rng.uniform(0.1, 0.3)), anchor=False)
        )
    _ensure_body_anchor(blocks, sent, budget)
    return _document("oversized-blocks", blocks, sent)


def _generate_tiny_sections(rng: random.Random, budget: int) -> RandomSplitDocument:
    sent = _Sentinels(rng)
    blocks: list[str] = [f"# {_heading_title(sent)}"]
    for _ in range(rng.randint(12, 30)):
        blocks.append(f"{'#' * rng.choice((2, 2, 2, 3))} {_heading_title(sent)}")
        choice = rng.random()
        if choice < 0.55:
            continue
        if choice < 0.9:
            blocks.append(_one_line_body(sent))
        else:
            blocks.append(_list(sent, depth=1, items=2))
    _ensure_body_anchor(blocks, sent, budget)
    return _document("tiny-sections", blocks, sent)


def _generate_edge_degenerate(rng: random.Random, budget: int) -> RandomSplitDocument:
    variant = rng.choice(("no-headings", "single-giant", "only-code", "long-titles"))
    sent = _Sentinels(rng)
    blocks: list[str] = []
    if variant == "no-headings":
        for _ in range(rng.randint(6, 14)):
            blocks.append(_paragraph(sent, int(budget * rng.uniform(0.1, 0.6))))
    elif variant == "single-giant":
        blocks.append(f"# {_heading_title(sent)}")
        blocks.append(_paragraph(sent, int(budget * rng.uniform(2.0, 3.0))))
    elif variant == "only-code":
        blocks.append(f"# {_heading_title(sent)}")
        blocks.append(_paragraph(sent, max(8, budget // 10)))
        for _ in range(rng.randint(2, 5)):
            if rng.random() < 0.6:
                size = int(budget * rng.uniform(0.8, 2.5))
            else:
                size = int(budget * rng.uniform(0.1, 0.5))
            blocks.append(_code_fence(sent, size))
    else:
        for index in range(rng.randint(3, 8)):
            level = 1 if index == 0 else rng.choice((2, 3))
            blocks.append(f"{'#' * level} {' '.join(sent.body.words(30, 80))}")
            blocks.append(_one_line_body(sent))
    _ensure_body_anchor(blocks, sent, budget)
    return _document("edge-degenerate", blocks, sent, variant=variant)


SHAPES: dict[str, Callable[[random.Random, int], RandomSplitDocument]] = {
    "deep-tree": _generate_deep_tree,
    "wide-flat": _generate_wide_flat,
    "long-sections": _generate_long_sections,
    "oversized-blocks": _generate_oversized_blocks,
    "tiny-sections": _generate_tiny_sections,
    "edge-degenerate": _generate_edge_degenerate,
}


def generate_documents(
    shapes: list[str],
    *,
    seed: int,
    count_per_shape: int,
    budget_tokens: int,
) -> list[RandomSplitDocument]:
    """Deterministically generate synthetic documents for every requested shape."""
    unknown = sorted(name for name in shapes if name not in SHAPES)
    if unknown:
        raise ValueError(f"unknown random splitter corpus shapes: {unknown}")
    if budget_tokens <= 0:
        raise ValueError("budget_tokens must be positive")
    documents: list[RandomSplitDocument] = []
    for name in shapes:
        generate = SHAPES[name]
        for index in range(count_per_shape):
            rng = random.Random(f"{seed}:{name}:{index}".encode())
            document = generate(rng, budget_tokens)
            documents.append(
                replace(
                    document,
                    dataset=f"synthetic-{name}",
                    document_id=f"synthetic-{name}-{index:06d}",
                )
            )
    return documents


# ---------------------------------------------------------------------------
# Structural profile


def _profile(source: str) -> dict[str, Any]:
    lines = source.splitlines()
    heading_levels = [
        len(match.group(1)) for match in re.finditer(r"(?m)^(#{1,6}) ", source)
    ]
    stack: list[int] = []
    depth = 0
    for level in heading_levels:
        while stack and stack[-1] >= level:
            stack.pop()
        stack.append(level)
        depth = max(depth, len(stack))
    fence_tokens: list[int] = []
    fence_lines: list[str] = []
    inside_fence = False
    for line in lines:
        if line.startswith("```") or line.startswith("~~~"):
            if inside_fence:
                fence_tokens.append(_size_tokens("\n".join(fence_lines)))
            fence_lines = []
            inside_fence = not inside_fence
            continue
        if inside_fence:
            fence_lines.append(line)
    tables = sum(1 for line in lines if re.match(r"^\|[\s:|-]+\|?\s*$", line))
    list_items = sum(1 for line in lines if re.match(r"^\s*(?:[-*+] |\d+\. )", line))
    return {
        "headings": len(heading_levels),
        "max_heading_depth": depth,
        "code_fences": len(fence_tokens),
        "max_code_fence_tokens": max(fence_tokens, default=0),
        "tables": tables,
        "list_items": list_items,
        "source_bytes": len(source.encode("utf-8")),
        "approx_tokens": _size_tokens(source),
    }


# ---------------------------------------------------------------------------
# Real-corpus recombination


_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*\n?", re.DOTALL)
_HEADING_START_RE = re.compile(r"(?m)^#{1,6} ")
_FENCE_LINE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})", re.MULTILINE)


def _strip_front_matter(text: str) -> str:
    return _FRONT_MATTER_RE.sub("", text, count=1)


def _fences_balanced(text: str) -> bool:
    return sum(1 for _ in _FENCE_LINE_RE.finditer(text)) % 2 == 0


def _split_sections(text: str) -> list[str]:
    """Split at ATX headings, dropping pieces with unbalanced fences."""
    trimmed = text.strip()
    if not trimmed:
        return []
    matches = list(_HEADING_START_RE.finditer(trimmed))
    if not matches:
        return [trimmed] if _fences_balanced(trimmed) else []
    pieces: list[str] = []
    preamble = trimmed[: matches[0].start()].strip()
    if preamble:
        pieces.append(preamble)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(trimmed)
        pieces.append(trimmed[match.start() : end].strip())
    return [piece for piece in pieces if piece and _fences_balanced(piece)]


def _load_recombination_pool(
    corpus_root: Path,
    manifest_path: Path,
    *,
    seed: int,
    pool_per_source: int,
) -> list[tuple[str, str, list[str]]]:
    """Load markdown documents from fetched corpora and split them into sections."""
    manifest = _load_manifest(manifest_path)
    pool: list[tuple[str, str, list[str]]] = []
    skipped: list[str] = []
    for source in manifest["sources"]:
        if str(source.get("format", "")) != "markdown":
            continue
        loader = str(source.get("loader") or source["kind"])
        try:
            if loader == "commonmark-json":
                documents = _commonmark_documents(source, corpus_root)
            elif loader == "git":
                documents = _git_documents(source, corpus_root)
            elif loader == "local-cases-json":
                documents = _local_case_documents(source, manifest_path)
            else:
                continue
        except FileNotFoundError:
            skipped.append(str(source["id"]))
            continue
        if len(documents) > pool_per_source:
            sample_rng = random.Random(f"{seed}:pool:{source['id']}".encode())
            indexes = sorted(sample_rng.sample(range(len(documents)), pool_per_source))
            documents = [documents[index] for index in indexes]
        source_id = str(source["id"])
        for document in documents:
            payload = document.load()
            if not isinstance(payload, str):
                continue
            sections = [
                section
                for section in _split_sections(_strip_front_matter(payload))
                if len(section.encode("utf-8")) <= RECOMBINED_MAX_BYTES
            ]
            if sections:
                pool.append((source_id, document.document_id, sections))
    if not pool:
        hint = ", ".join(skipped) if skipped else "none declared"
        raise FileNotFoundError(
            "no fetched Markdown corpora available for recombination "
            f"(missing or empty: {hint}); run "
            "`uv run python -m benchmarks.fetch_parser_corpora` first "
            "or pass --corpus synthetic"
        )
    return pool


def recombine_documents(
    *,
    seed: int,
    count: int,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    pool_per_source: int = 300,
) -> list[RandomSplitDocument]:
    """Deterministically stitch random section spans from real corpora."""
    pool = _load_recombination_pool(
        corpus_root, manifest_path, seed=seed, pool_per_source=pool_per_source
    )
    documents: list[RandomSplitDocument] = []
    for index in range(count):
        rng = random.Random(f"{seed}:recombined:{index}".encode())
        pieces: list[str] = []
        total_bytes = 0
        for _ in range(rng.randint(3, 8)):
            _, _, sections = pool[rng.randrange(len(pool))]
            start = rng.randrange(len(sections))
            span = rng.randint(1, min(4, len(sections) - start))
            for section in sections[start : start + span]:
                size = len(section.encode("utf-8"))
                if total_bytes + size > RECOMBINED_MAX_BYTES:
                    break
                pieces.append(section)
                total_bytes += size
        if not pieces:
            _, _, sections = pool[rng.randrange(len(pool))]
            pieces = [sections[rng.randrange(len(sections))]]
        source = "\n\n".join(pieces) + "\n"
        documents.append(
            RandomSplitDocument(
                dataset="recombined",
                document_id=f"recombined-{index:06d}",
                shape="recombined",
                source=source,
                required_content=(),
                protected_content=(),
                profile=_profile(source),
            )
        )
    return documents


__all__ = [
    "RECOMBINED_MAX_BYTES",
    "SHAPES",
    "RandomSplitDocument",
    "generate_documents",
    "recombine_documents",
]
