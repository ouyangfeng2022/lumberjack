"""Optional Tree-sitter support for source declaration extraction."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Literal, TypeAlias

CodeLanguage: TypeAlias = Literal[
    "python",
    "javascript",
    "typescript",
    "bash",
    "c",
    "cpp",
    "csharp",
    "go",
    "java",
    "kotlin",
    "lua",
    "php",
    "ruby",
    "rust",
    "swift",
    "zig",
]


@dataclass(frozen=True)
class SyntaxSymbol:
    """A named, top-level declaration selected from a concrete syntax tree."""

    text: str
    name: str
    kind: str
    start_byte: int
    end_byte: int
    line_start: int
    line_end: int
    has_syntax_error: bool


_LANGUAGE_SPECS: dict[CodeLanguage, tuple[str, str, frozenset[str]]] = {
    "python": (
        "tree_sitter_python",
        "language",
        frozenset({"class_definition", "function_definition"}),
    ),
    "javascript": (
        "tree_sitter_javascript",
        "language",
        frozenset(
            {
                "class_declaration",
                "function_declaration",
                "generator_function_declaration",
                "lexical_declaration",
                "variable_declaration",
            }
        ),
    ),
    "typescript": (
        "tree_sitter_typescript",
        "language_typescript",
        frozenset(
            {
                "abstract_class_declaration",
                "class_declaration",
                "enum_declaration",
                "function_declaration",
                "generator_function_declaration",
                "interface_declaration",
                "lexical_declaration",
                "type_alias_declaration",
                "variable_declaration",
            }
        ),
    ),
    "bash": ("tree_sitter_bash", "language", frozenset({"function_definition"})),
    "c": (
        "tree_sitter_c",
        "language",
        frozenset({"function_definition", "type_definition"}),
    ),
    "cpp": (
        "tree_sitter_cpp",
        "language",
        frozenset(
            {
                "class_specifier",
                "function_definition",
                "namespace_definition",
                "struct_specifier",
                "type_definition",
            }
        ),
    ),
    "csharp": (
        "tree_sitter_c_sharp",
        "language",
        frozenset(
            {
                "class_declaration",
                "enum_declaration",
                "interface_declaration",
                "struct_declaration",
            }
        ),
    ),
    "go": (
        "tree_sitter_go",
        "language",
        frozenset({"function_declaration", "method_declaration", "type_declaration"}),
    ),
    "java": (
        "tree_sitter_java",
        "language",
        frozenset(
            {
                "class_declaration",
                "enum_declaration",
                "interface_declaration",
                "record_declaration",
            }
        ),
    ),
    "kotlin": (
        "tree_sitter_kotlin",
        "language",
        frozenset(
            {
                "class_declaration",
                "function_declaration",
                "interface_declaration",
                "object_declaration",
            }
        ),
    ),
    "lua": (
        "tree_sitter_lua",
        "language",
        frozenset({"function_declaration", "function_definition"}),
    ),
    "php": (
        "tree_sitter_php",
        "language_php",
        frozenset(
            {
                "class_declaration",
                "function_definition",
                "interface_declaration",
                "trait_declaration",
            }
        ),
    ),
    "ruby": (
        "tree_sitter_ruby",
        "language",
        frozenset({"class", "method", "module", "singleton_method"}),
    ),
    "rust": (
        "tree_sitter_rust",
        "language",
        frozenset(
            {
                "enum_item",
                "function_item",
                "impl_item",
                "struct_item",
                "trait_item",
                "type_item",
            }
        ),
    ),
    "swift": (
        "tree_sitter_swift",
        "language",
        frozenset(
            {
                "class_declaration",
                "enum_declaration",
                "function_declaration",
                "protocol_declaration",
                "struct_declaration",
            }
        ),
    ),
    "zig": (
        "tree_sitter_zig",
        "language",
        frozenset({"function_declaration", "variable_declaration"}),
    ),
}


def extract_top_level_symbols(
    source: str, language: CodeLanguage
) -> tuple[SyntaxSymbol, ...] | None:
    """Return syntax-aware declarations, or ``None`` when the extra is absent."""

    try:
        tree_sitter = import_module("tree_sitter")
        module_name, factory_name, declaration_types = _LANGUAGE_SPECS[language]
        grammar = import_module(module_name)
    except ImportError:
        return None

    language_factory = getattr(grammar, factory_name)
    parser = tree_sitter.Parser(tree_sitter.Language(language_factory()))
    source_bytes = source.encode("utf-8")
    root = parser.parse(source_bytes).root_node
    symbols: list[SyntaxSymbol] = []
    for node in _top_level_declarations(root, declaration_types):
        declaration, range_node = _declaration(node)
        if declaration is None or declaration.type not in declaration_types:
            continue
        name = _declaration_name(declaration)
        if name is None:
            continue
        symbols.append(
            SyntaxSymbol(
                text=source_bytes[range_node.start_byte : range_node.end_byte].decode(
                    "utf-8"
                ),
                name=name,
                kind=declaration.type,
                start_byte=range_node.start_byte,
                end_byte=range_node.end_byte,
                line_start=range_node.start_point.row + 1,
                line_end=max(
                    range_node.start_point.row + 1,
                    range_node.end_point.row
                    + (1 if range_node.end_point.column > 0 else 0),
                ),
                has_syntax_error=root.has_error,
            )
        )
    return tuple(symbols)


def _top_level_declarations(
    root: Any, declaration_types: frozenset[str]
) -> tuple[Any, ...]:
    declarations: list[Any] = []
    for node in root.named_children:
        declaration, _ = _declaration(node)
        if declaration is not None and declaration.type in declaration_types:
            declarations.append(node)
        elif declaration is not None and declaration.type in {
            "declaration_list",
            "namespace_declaration",
            "file_scoped_namespace_declaration",
        }:
            declarations.extend(_top_level_declarations(declaration, declaration_types))
    return tuple(declarations)


def _declaration(node: Any) -> tuple[Any | None, Any]:
    """Unwrap export/decorator wrappers while retaining their source range."""

    range_node = node
    while node.type in {"decorated_definition", "export_statement"}:
        node = node.child_by_field_name(
            "definition" if node.type == "decorated_definition" else "declaration"
        )
        if node is None:
            return None, range_node
    return node, range_node


def _declaration_name(node: Any) -> str | None:
    name = node.child_by_field_name("name")
    if name is not None:
        return name.text.decode("utf-8")
    for child in node.named_children:
        if child.type == "variable_declarator":
            name = child.child_by_field_name("name")
            if name is not None:
                return name.text.decode("utf-8")
    for child in node.children:
        if child.type in {
            "identifier",
            "name",
            "simple_identifier",
            "type_identifier",
            "constant",
            "word",
        }:
            return child.text.decode("utf-8")
        nested = _declaration_name(child)
        if nested is not None:
            return nested
    return None


__all__ = ["CodeLanguage", "SyntaxSymbol", "extract_top_level_symbols"]
