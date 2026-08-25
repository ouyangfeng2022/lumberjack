"""Large-corpus, deterministic benchmark for the Markdown, HTML, and DOCX parsers."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import random
import re
import statistics
import subprocess
import sys
import time
import tracemalloc
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser as _StdlibHTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from benchmarks.parser_contract import (
    PARSER_BENCHMARK_SCHEMA_VERSION,
    ParserBenchmarkConfig,
    ParserBenchmarkReport,
    ParserDocumentResult,
)
from lumberjack.models import DocTree, DocumentBlock, DocumentInline, SectionNode
from lumberjack.parser.docx import DocxParser
from lumberjack.parser.html import HTMLParser
from lumberjack.parser.markdown import MarkdownParser

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "datasets" / "parser_sources.json"
DEFAULT_CORPUS_ROOT = ROOT / "datasets" / "external"
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class CorpusDocument:
    dataset_id: str
    document_id: str
    format: str
    source_bytes: int
    load: Callable[[], str | bytes]
    reference_text: str | None = None
    required_elements: tuple[str, ...] = ()
    forbidden_elements: tuple[str, ...] = ()


class _HTMLTextExtractor(_StdlibHTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "head", "template", "title"}:
            self._skip_depth += 1
        elif tag == "img" and self._skip_depth == 0:
            alt = next((value for name, value in attrs if name == "alt"), None)
            if alt:
                self.parts.append(alt)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "head", "template", "title"}:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)


def _safe_child(root: Path, *parts: str) -> Path:
    """Resolve a manifest path and require it to remain below its declared root."""
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValueError(f"parser corpus path escapes its root: {candidate}")
    return candidate


def _html_text(source: str) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(source)
    extractor.close()
    return " ".join(extractor.parts)


def _html_visible_text(source: str) -> str:
    """Independent visible-text reference for HTML corpus documents.

    Mirrors the body text a browser shows: text nodes plus image alt text,
    excluding ``script``/``style``/``template``, and ``title``/``head``-only
    content. Parts are joined with spaces so block-level splits in the tree
    do not glue separate words together.
    """
    extractor = _HTMLTextExtractor()
    extractor.feed(source)
    extractor.close()
    return " ".join(extractor.parts)


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=ROOT.parent
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _git_status() -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "status", "--short"], text=True, cwd=ROOT.parent
        )
    except (OSError, subprocess.CalledProcessError):
        return ["unavailable"]
    return output.splitlines()


def _load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list):
        raise ValueError("parser source manifest must contain a sources array")
    return manifest


def _commonmark_documents(source: dict[str, Any], root: Path) -> list[CorpusDocument]:
    path = _safe_child(root, str(source["id"]), str(source["target"]))
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != source["sha256"]:
        raise ValueError(f"CommonMark corpus checksum mismatch: {path}")
    cases = json.loads(payload)
    documents: list[CorpusDocument] = []
    for case in cases:
        markdown = str(case["markdown"])
        example = int(case["example"])
        documents.append(
            CorpusDocument(
                dataset_id=str(source["id"]),
                document_id=f"example-{example:04d}",
                format="markdown",
                source_bytes=len(markdown.encode("utf-8")),
                load=lambda markdown=markdown: markdown,
                reference_text=_html_text(str(case["html"])),
            )
        )
    return documents


def _git_documents(source: dict[str, Any], root: Path) -> list[CorpusDocument]:
    repository_root = _safe_child(root, str(source["id"]))
    if not repository_root.is_dir():
        raise FileNotFoundError(f"parser corpus is not fetched: {repository_root}")
    expected_revision = source.get("revision")
    if expected_revision is not None:
        try:
            current_revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repository_root,
                text=True,
            ).strip()
            worktree_status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=repository_root,
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError) as error:
            raise RuntimeError(f"cannot verify parser corpus {source['id']}") from error
        if current_revision != str(expected_revision):
            raise RuntimeError(
                f"parser corpus {source['id']} is at {current_revision}, "
                f"expected {expected_revision}"
            )
        if worktree_status:
            raise RuntimeError(f"parser corpus {source['id']} has local changes")
    patterns = [str(pattern) for pattern in source["include"]]
    if any(
        Path(pattern).is_absolute() or ".." in Path(pattern).parts
        for pattern in patterns
    ):
        raise ValueError(f"unsafe include pattern for parser corpus {source['id']}")
    paths = sorted(
        {
            path
            for pattern in patterns
            for path in repository_root.glob(pattern)
            if path.is_file()
        }
    )
    source_format = str(source["format"])
    if source_format not in {"markdown", "docx", "html"}:
        raise ValueError(f"unsupported parser corpus format: {source_format!r}")
    documents: list[CorpusDocument] = []
    for path in paths:
        relative_path = path.relative_to(repository_root).as_posix()
        load: Callable[[], str | bytes]
        if source_format == "docx":
            load = lambda path=path: path.read_bytes()  # noqa: E731
        else:
            load = lambda path=path: path.read_text(encoding="utf-8")  # noqa: E731
        documents.append(
            CorpusDocument(
                dataset_id=str(source["id"]),
                document_id=relative_path,
                format=source_format,
                source_bytes=path.stat().st_size,
                load=load,
            )
        )
    return documents


def _html5lib_documents(source: dict[str, Any], root: Path) -> list[CorpusDocument]:
    """Load html5lib tree-construction ``.dat`` cases as HTML fragments."""
    repository_root = _safe_child(root, str(source["id"]))
    if not repository_root.is_dir():
        raise FileNotFoundError(f"parser corpus is not fetched: {repository_root}")
    patterns = [str(pattern) for pattern in source["include"]]
    paths = sorted(
        {
            path
            for pattern in patterns
            for path in repository_root.glob(pattern)
            if path.is_file()
        }
    )
    documents: list[CorpusDocument] = []
    for path in paths:
        relative_path = path.relative_to(repository_root).as_posix()
        content = path.read_text(encoding="utf-8")
        case_lines: list[str] = []
        case_index = 0
        in_data = False
        for line in content.splitlines():
            if line == "#data":
                if case_lines:
                    documents.append(
                        _html5lib_case(source, relative_path, case_index, case_lines)
                    )
                case_index += 1
                case_lines = []
                in_data = True
                continue
            if line.startswith("#"):
                in_data = False
                continue
            if in_data:
                case_lines.append(line)
        if case_lines:
            documents.append(
                _html5lib_case(source, relative_path, case_index, case_lines)
            )
    return documents


def _html5lib_case(
    source: dict[str, Any],
    relative_path: str,
    case_index: int,
    lines: list[str],
) -> CorpusDocument:
    fragment = "\n".join(lines)
    return CorpusDocument(
        dataset_id=str(source["id"]),
        document_id=f"{relative_path}#case-{case_index}",
        format="html",
        source_bytes=len(fragment.encode("utf-8")),
        load=lambda fragment=fragment: fragment,
    )


def _local_case_documents(
    source: dict[str, Any], manifest_path: Path
) -> list[CorpusDocument]:
    path = _safe_child(manifest_path.parent, str(source["target"]))
    cases = json.loads(path.read_text(encoding="utf-8"))
    return [
        CorpusDocument(
            dataset_id=str(source["id"]),
            document_id=str(case["id"]),
            format="markdown",
            source_bytes=len(str(case["source"]).encode("utf-8")),
            load=lambda case=case: str(case["source"]),
            required_elements=tuple(str(item) for item in case["required_elements"]),
            forbidden_elements=tuple(
                str(item) for item in case.get("forbidden_elements", [])
            ),
        )
        for case in cases
    ]


def discover_documents(
    corpus_root: Path,
    config: ParserBenchmarkConfig,
    *,
    source_ids: set[str] | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> tuple[str, dict[str, int], dict[str, int], list[CorpusDocument]]:
    """Discover and deterministically sample eligible documents per source."""
    manifest = _load_manifest(manifest_path)
    selected: list[CorpusDocument] = []
    candidates_by_source: dict[str, int] = {}
    selected_by_source: dict[str, int] = {}
    known_sources: set[str] = set()
    for source in manifest["sources"]:
        source_id = str(source["id"])
        known_sources.add(source_id)
        if source_ids is not None and source_id not in source_ids:
            continue
        loader = str(source.get("loader") or source["kind"])
        if loader == "commonmark-json":
            candidates = _commonmark_documents(source, corpus_root)
        elif loader == "git":
            candidates = _git_documents(source, corpus_root)
        elif loader == "html5lib-dat":
            candidates = _html5lib_documents(source, corpus_root)
        elif loader == "local-cases-json":
            candidates = _local_case_documents(source, manifest_path)
        else:
            raise ValueError(f"unsupported parser corpus loader: {loader!r}")
        candidates = [
            item
            for item in candidates
            if item.source_bytes <= config.max_document_bytes
        ]
        candidates_by_source[source_id] = len(candidates)
        limit = config.sample_size_per_source
        if limit and len(candidates) > limit:
            seed_bytes = hashlib.sha256(f"{config.seed}:{source_id}".encode()).digest()
            source_random = random.Random(int.from_bytes(seed_bytes[:8], "big"))
            candidates = source_random.sample(candidates, limit)
            candidates.sort(key=lambda item: item.document_id)
        selected_by_source[source_id] = len(candidates)
        selected.extend(candidates)

    unknown = (source_ids or set()) - known_sources
    if unknown:
        raise ValueError(f"unknown parser corpus sources: {sorted(unknown)}")
    return (
        str(manifest["dataset_version"]),
        candidates_by_source,
        selected_by_source,
        selected,
    )


def _walk_sections(section: SectionNode) -> Iterable[SectionNode]:
    yield section
    for child in section.children:
        yield from _walk_sections(child)


def _walk_blocks(blocks: Iterable[DocumentBlock]) -> Iterable[DocumentBlock]:
    for block in blocks:
        yield block
        yield from _walk_blocks(block.children)


def _walk_inlines(inlines: Iterable[DocumentInline]) -> Iterable[DocumentInline]:
    for inline in inlines:
        yield inline
        yield from _walk_inlines(inline.children)


def _validate_tree(tree: DocTree) -> list[str]:
    diagnostics: list[str] = []
    if tree.root.level != 0:
        diagnostics.append("root level is not zero")
    if tree.root.title != tree.title:
        diagnostics.append("root title differs from document title")
    for section in _walk_sections(tree.root):
        for index, child in enumerate(section.children):
            if child.index != index:
                diagnostics.append(f"non-contiguous section index at {child.path!r}")
            if child.level <= section.level:
                diagnostics.append(f"non-increasing heading level at {child.path!r}")
            if child.path != (*section.path, (child.level, child.title)):
                diagnostics.append(f"invalid heading path at {child.path!r}")
        for block in _walk_blocks(section.blocks):
            if not block.text:
                diagnostics.append(f"empty {block.kind} block")
            if (block.start_line is None) != (block.end_line is None):
                diagnostics.append(f"partial source range on {block.kind} block")
            if (
                block.start_line is not None
                and block.end_line is not None
                and block.start_line > block.end_line
            ):
                diagnostics.append(f"reversed source range on {block.kind} block")
    return diagnostics


def _tree_text(tree: DocTree) -> str:
    parts = [section.title for section in _walk_sections(tree.root) if section.level]
    for section in _walk_sections(tree.root):
        for block in section.blocks:
            parts.append(block.text)
    return "\n".join(parts)


def _docx_visible_text(payload: bytes) -> str:
    with zipfile.ZipFile(BytesIO(payload)) as package:
        document_xml = package.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    paragraphs: list[str] = []

    def local_name(element: ElementTree.Element) -> str:
        return str(element.tag).rsplit("}", 1)[-1]

    def alternate_content(element: ElementTree.Element) -> ElementTree.Element | None:
        return next(
            (child for child in element if local_name(child) == "Fallback"),
            None,
        )

    def inline_text(element: ElementTree.Element, hidden: bool = False) -> str:
        name = local_name(element)
        hidden = hidden or name in {"del", "moveFrom"}
        if hidden:
            return ""
        if name == "AlternateContent":
            fallback = alternate_content(element)
            return inline_text(fallback) if fallback is not None else ""
        if name == "t" and element.text:
            return element.text
        if name == "tab":
            return "\t"
        if name in {"br", "cr"}:
            return "\n"
        return "".join(inline_text(child, hidden) for child in element)

    def visit(element: ElementTree.Element, hidden: bool = False) -> None:
        name = local_name(element)
        hidden = hidden or name in {"del", "moveFrom"}
        if hidden:
            return
        if name == "AlternateContent":
            fallback = alternate_content(element)
            if fallback is not None:
                visit(fallback)
            return
        if name == "p":
            paragraphs.append(inline_text(element))
            return
        for child in element:
            visit(child)

    visit(root)
    return "\n".join(paragraphs)


def _tokens(text: str) -> Counter[str]:
    return Counter(
        match.group(0).casefold() for match in WORD_RE.finditer(html.unescape(text))
    )


def _content_token_stats(
    source_text: str, extracted_text: str
) -> tuple[int, int, float]:
    source_tokens = _tokens(source_text)
    if not source_tokens:
        return (0, 0, 1.0)
    extracted_tokens = _tokens(extracted_text)
    source_count = sum(source_tokens.values())
    matched_count = sum((source_tokens & extracted_tokens).values())
    return (source_count, matched_count, matched_count / source_count)


def _content_character_stats(
    source_text: str, extracted_text: str
) -> tuple[int, int, float]:
    source_characters = Counter(
        character.casefold()
        for character in html.unescape(source_text)
        if not character.isspace()
    )
    if not source_characters:
        return (0, 0, 1.0)
    extracted_characters = Counter(
        character.casefold()
        for character in html.unescape(extracted_text)
        if not character.isspace()
    )
    source_count = sum(source_characters.values())
    matched_count = sum((source_characters & extracted_characters).values())
    return (source_count, matched_count, matched_count / source_count)


def _structure_counts(tree: DocTree) -> dict[str, int]:
    sections = list(_walk_sections(tree.root))
    blocks = [block for section in sections for block in _walk_blocks(section.blocks)]
    inlines = [
        inline
        for section in sections
        for block in _walk_blocks(section.blocks)
        for inline in _walk_inlines(block.inlines)
    ]
    return {
        "section_count": max(0, len(sections) - 1),
        "block_count": len(blocks),
        "inline_count": len(inlines),
        "table_count": sum(block.kind in {"table", "html_table"} for block in blocks),
        "list_count": sum(block.kind == "list" for block in blocks),
        "image_count": sum(inline.kind == "image" for inline in inlines),
    }


def _element_signatures(tree: DocTree) -> Counter[str]:
    sections = list(_walk_sections(tree.root))
    blocks = [block for section in sections for block in _walk_blocks(section.blocks)]
    inlines = [
        inline
        for section in sections
        for block in _walk_blocks(section.blocks)
        for inline in _walk_inlines(block.inlines)
    ]
    signatures = Counter(f"section:h{section.level}" for section in sections[1:])
    signatures.update(f"block:{block.kind}" for block in blocks)
    signatures.update(f"inline:{inline.kind}" for inline in inlines)
    signatures.update(
        "reference_definition" for _ in tree.reference_definitions.values()
    )
    return signatures


def _check_elements(
    tree: DocTree, document: CorpusDocument
) -> tuple[int, int, list[str]]:
    actual = _element_signatures(tree)
    required = Counter(document.required_elements)
    passed = sum(min(count, actual[element]) for element, count in required.items())
    diagnostics = [
        f"missing element {element!r}: expected {count}, found {actual[element]}"
        for element, count in required.items()
        if actual[element] < count
    ]
    for element in document.forbidden_elements:
        if actual[element] == 0:
            passed += 1
        else:
            diagnostics.append(
                f"unexpected element {element!r}: found {actual[element]}"
            )
    total = sum(required.values()) + len(document.forbidden_elements)
    return total, passed, diagnostics


def _parse_document(document: CorpusDocument) -> ParserDocumentResult:
    payload = document.load()
    digest = hashlib.sha256(
        payload.encode("utf-8") if isinstance(payload, str) else payload
    ).hexdigest()
    tracemalloc.start()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        if document.format == "markdown":
            tree = MarkdownParser().parse(
                payload if isinstance(payload, str) else "",
                document_title=document.document_id,
            )
        elif document.format == "html":
            tree = HTMLParser().parse(
                payload if isinstance(payload, str) else "",
                document_title=document.document_id,
            )
        else:
            tree = DocxParser().parse(
                payload if isinstance(payload, bytes) else b"",
                document_title=document.document_id,
            )
        diagnostics = _validate_tree(tree)
        element_assertions, passed_element_assertions, element_diagnostics = (
            _check_elements(tree, document)
        )
        diagnostics.extend(element_diagnostics)
        if document.reference_text is not None:
            source_text = document.reference_text
        elif isinstance(payload, str):
            source_text = (
                _html_visible_text(payload) if document.format == "html" else payload
            )
        else:
            source_text = _docx_visible_text(payload)
        extracted_text = _tree_text(tree)
        source_token_count, matched_token_count, recall = _content_token_stats(
            source_text, extracted_text
        )
        source_character_count, matched_character_count, character_recall = (
            _content_character_stats(source_text, extracted_text)
        )
        counts = _structure_counts(tree)
        status = "invalid" if diagnostics else "success"
        error_type = None
        error_message = None
    except Exception as error:  # benchmark must preserve each corpus failure
        diagnostics = []
        recall = None
        source_token_count = 0
        matched_token_count = 0
        character_recall = None
        source_character_count = 0
        matched_character_count = 0
        counts = {
            "section_count": 0,
            "block_count": 0,
            "inline_count": 0,
            "table_count": 0,
            "list_count": 0,
            "image_count": 0,
        }
        element_assertions = len(document.required_elements) + len(
            document.forbidden_elements
        )
        passed_element_assertions = 0
        status = "error"
        error_type = type(error).__name__
        error_message = str(error)
    finally:
        wall_time = time.perf_counter() - wall_start
        cpu_time = time.process_time() - cpu_start
        peak_memory = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    return ParserDocumentResult(
        dataset_id=document.dataset_id,
        document_id=document.document_id,
        format=document.format,
        sha256=digest,
        source_bytes=document.source_bytes,
        status=status,
        wall_time_seconds=wall_time,
        cpu_time_seconds=cpu_time,
        peak_memory_bytes=peak_memory,
        content_token_recall=recall,
        source_token_count=source_token_count,
        matched_token_count=matched_token_count,
        content_character_recall=character_recall,
        source_character_count=source_character_count,
        matched_character_count=matched_character_count,
        element_assertions=element_assertions,
        passed_element_assertions=passed_element_assertions,
        element_accuracy=(
            passed_element_assertions / element_assertions
            if element_assertions
            else None
        ),
        error_type=error_type,
        error_message=error_message,
        diagnostics=tuple(diagnostics),
        **counts,
    )


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * ratio)]


def _summarize_group(results: list[ParserDocumentResult]) -> dict[str, Any]:
    successful = [result for result in results if result.status == "success"]
    recalls = [
        result.content_token_recall
        for result in successful
        if result.content_token_recall is not None
    ]
    character_recalls = [
        result.content_character_recall
        for result in successful
        if result.content_character_recall is not None
    ]
    total_wall = sum(result.wall_time_seconds for result in results)
    errors = Counter(
        result.error_type or result.status
        for result in results
        if result.status != "success"
    )
    element_assertions = sum(result.element_assertions for result in results)
    passed_element_assertions = sum(
        result.passed_element_assertions for result in results
    )
    return {
        "documents": len(results),
        "successful": len(successful),
        "failed_or_invalid": len(results) - len(successful),
        "success_rate": len(successful) / len(results) if results else 0.0,
        "source_bytes": sum(result.source_bytes for result in results),
        "throughput_mb_per_second": (
            sum(result.source_bytes for result in results) / 1_000_000 / total_wall
            if total_wall
            else 0.0
        ),
        "wall_time_seconds_p50": _percentile(
            [result.wall_time_seconds for result in results], 0.5
        ),
        "wall_time_seconds_p95": _percentile(
            [result.wall_time_seconds for result in results], 0.95
        ),
        "peak_memory_bytes_p95": _percentile(
            [float(result.peak_memory_bytes) for result in results], 0.95
        ),
        "content_token_recall_mean": statistics.fmean(recalls) if recalls else 0.0,
        "content_token_recall_p05": _percentile(recalls, 0.05),
        "content_token_recall_min": min(recalls, default=0.0),
        "documents_below_recall_0_99": sum(recall < 0.99 for recall in recalls),
        "documents_below_recall_0_95": sum(recall < 0.95 for recall in recalls),
        "content_character_recall_mean": (
            statistics.fmean(character_recalls) if character_recalls else 0.0
        ),
        "content_character_recall_min": min(character_recalls, default=0.0),
        "documents_below_character_recall_0_99": sum(
            recall < 0.99 for recall in character_recalls
        ),
        "element_assertions": element_assertions,
        "passed_element_assertions": passed_element_assertions,
        "element_accuracy": (
            passed_element_assertions / element_assertions
            if element_assertions
            else None
        ),
        "errors": dict(sorted(errors.items())),
    }


def summarize_results(results: list[ParserDocumentResult]) -> dict[str, Any]:
    formats = sorted({result.format for result in results})
    datasets = sorted({result.dataset_id for result in results})
    return {
        "overall": _summarize_group(results),
        "by_format": {
            source_format: _summarize_group(
                [result for result in results if result.format == source_format]
            )
            for source_format in formats
        },
        "by_dataset": {
            dataset: _summarize_group(
                [result for result in results if result.dataset_id == dataset]
            )
            for dataset in datasets
        },
    }


def run_parser_benchmark(
    config: ParserBenchmarkConfig,
    *,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    source_ids: set[str] | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> ParserBenchmarkReport:
    dataset_version, candidates, selected, documents = discover_documents(
        corpus_root,
        config,
        source_ids=source_ids,
        manifest_path=manifest_path,
    )
    results = [_parse_document(document) for document in documents]
    return ParserBenchmarkReport(
        schema_version=PARSER_BENCHMARK_SCHEMA_VERSION,
        commit=_commit(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        environment={
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "git_status": _git_status(),
        },
        config=config,
        dataset_version=dataset_version,
        candidates_by_source=candidates,
        selected_by_source=selected,
        results=results,
        summary=summarize_results(results),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark Markdown/DOCX parsing")
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--source", action="append", dest="sources")
    parser.add_argument("--seed", type=int, default=20260824)
    parser.add_argument("--sample-size-per-source", type=int, default=500)
    parser.add_argument("--max-document-bytes", type=int, default=20_000_000)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = ParserBenchmarkConfig(
        seed=args.seed,
        sample_size_per_source=args.sample_size_per_source,
        max_document_bytes=args.max_document_bytes,
    )
    report = run_parser_benchmark(
        config,
        corpus_root=args.corpus_root,
        source_ids=set(args.sources) if args.sources else None,
    )
    output = (
        args.output
        or ROOT / "results" / f"parser-{datetime.now():%Y%m%d}-{report.commit[:12]}"
    )
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "raw.json"
    raw_path.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schema_version": report.schema_version,
        "commit": report.commit,
        "dataset_version": report.dataset_version,
        "config": asdict(report.config),
        "candidates_by_source": report.candidates_by_source,
        "selected_by_source": report.selected_by_source,
        "summary": report.summary,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(raw_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
