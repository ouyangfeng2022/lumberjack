from __future__ import annotations

from pathlib import Path

import pytest

from lumberjack.parser import AutoParser, NotebookParser, SourceCodeParser, SQLParser
from lumberjack.parser.code import parser as code_parser
from lumberjack.parser.code.tree_sitter import CodeLanguage


def test_python_source_parser_preserves_symbols_and_lines() -> None:
    tree = SourceCodeParser(language="python").parse(
        "# note\ndef hello():\n    return 'hi'\n\nclass Guide:\n    pass\n"
    )

    assert [block.attrs["symbol"] for block in tree.root.blocks] == ["hello", "Guide"]
    assert tree.root.blocks[0].source_locations[0].line_start == 2


def test_notebook_parser_preserves_cell_order_and_language() -> None:
    tree = NotebookParser().parse(
        '{"metadata":{"kernelspec":{"language":"python"}},"cells":[{"cell_type":"code","source":["print(1)\\n"]},{"cell_type":"markdown","source":"# Guide"}]}'
    )

    assert [block.attrs["cell_type"] for block in tree.root.blocks] == [
        "code",
        "markdown",
    ]
    assert tree.root.blocks[1].source_locations[0].json_path == '$["cells"][1]'


def test_sql_parser_preserves_statement_order() -> None:
    tree = SQLParser().parse(
        "CREATE TABLE items (id INTEGER);\nINSERT INTO items VALUES (1);"
    )

    assert [block.attrs["statement_index"] for block in tree.root.blocks] == [0, 1]


def test_tree_sitter_enhancement_handles_exported_typescript_declarations() -> None:
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")

    tree = SourceCodeParser(language="typescript").parse(
        "export interface Config { enabled: boolean }\n"
        "export type Mode = 'fast' | 'safe'\n"
        "export class Runner { run(): void {} }\n"
    )

    assert [block.attrs["symbol"] for block in tree.root.blocks] == [
        "Config",
        "Mode",
        "Runner",
    ]
    assert {block.attrs["syntax_parser"] for block in tree.root.blocks} == {
        "tree-sitter"
    }
    assert tree.root.blocks[0].source_locations[0].byte_start == 0


def test_tree_sitter_enhancement_retains_valid_malformed_python_declaration() -> None:
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_python")

    tree = SourceCodeParser(language="python").parse(
        "def valid():\n    return 1\n\ndef broken(\n"
    )

    assert tree.root.blocks[0].attrs["symbol"] == "valid"
    assert tree.root.blocks[0].attrs["has_syntax_error"] is True


def test_source_code_parser_uses_builtin_fallback_without_extra(monkeypatch) -> None:
    monkeypatch.setattr(code_parser, "extract_top_level_symbols", lambda *_: None)

    tree = SourceCodeParser(language="javascript").parse(
        "export function greet() {}\nconst answer = 42;"
    )

    assert [block.attrs["symbol"] for block in tree.root.blocks] == [
        "greet",
        "answer",
    ]
    assert "syntax_parser" not in tree.root.blocks[0].attrs


@pytest.mark.parametrize(
    ("language", "source", "symbols"),
    [
        ("bash", "function go() { echo hi; }", ["go"]),
        ("c", "int add(void) { return 1; }", ["add"]),
        ("cpp", "class Runner {};", ["Runner"]),
        ("csharp", "namespace App { class Runner {} }", ["Runner"]),
        ("go", "func Run() {}", ["Run"]),
        ("java", "class Runner {}", ["Runner"]),
        ("kotlin", "fun run() {}", ["run"]),
        ("lua", "local function run() end", ["run"]),
        ("php", "<?php function run() {}", ["run"]),
        ("ruby", "class Runner\nend", ["Runner"]),
        ("rust", "fn run() {}", ["run"]),
        ("swift", "func run() {}", ["run"]),
        ("zig", "fn run() void {}", ["run"]),
    ],
)
def test_tree_sitter_registry_extracts_common_language_declarations(
    language: CodeLanguage, source: str, symbols: list[str]
) -> None:
    pytest.importorskip("tree_sitter")

    tree = SourceCodeParser(language=language).parse(source)

    assert [block.attrs["symbol"] for block in tree.root.blocks] == symbols
    assert {block.attrs["syntax_parser"] for block in tree.root.blocks} == {
        "tree-sitter"
    }


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        (".sh", "bash"),
        (".c", "c"),
        (".cpp", "cpp"),
        (".cs", "csharp"),
        (".go", "go"),
        (".java", "java"),
        (".kt", "kotlin"),
        (".lua", "lua"),
        (".php", "php"),
        (".rb", "ruby"),
        (".rs", "rust"),
        (".swift", "swift"),
        (".zig", "zig"),
    ],
)
def test_auto_parser_detects_registered_code_suffixes(
    suffix: str, expected: str
) -> None:
    assert AutoParser()._detect_format("", Path(f"example{suffix}"), "auto") == expected
