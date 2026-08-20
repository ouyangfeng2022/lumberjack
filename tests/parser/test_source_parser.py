from __future__ import annotations

from lumberjack.parser import NotebookParser, SourceCodeParser, SQLParser


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
