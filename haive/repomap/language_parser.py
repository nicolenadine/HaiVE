from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

_PY_LANGUAGE = Language(tspython.language())

PARSER_VERSION = "tree-sitter-python:0.25.0"
EXTRACTOR_VERSION = "1"


@dataclass
class ParsedSymbol:
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    signature: str | None


@dataclass
class ParsedReference:
    symbol_name: str
    line_number: int


@dataclass
class ParsedFile:
    symbols: list[ParsedSymbol] = field(default_factory=list)
    references: list[ParsedReference] = field(default_factory=list)
    content_hash: str = ""
    parser_version: str = PARSER_VERSION
    extractor_version: str = EXTRACTOR_VERSION


class LanguageParser(Protocol):
    extensions: list[str]
    language: str

    def parse_file(self, path: str, content: str) -> ParsedFile: ...


class PythonParser:
    extensions = [".py"]
    language = "python"

    def parse_file(self, path: str, content: str) -> ParsedFile:
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        parser = Parser(_PY_LANGUAGE)
        tree = parser.parse(content.encode())
        lines = content.splitlines()
        return ParsedFile(
            symbols=_extract_symbols(tree.root_node, lines),
            references=_extract_references(tree.root_node),
            content_hash=content_hash,
        )


# --- symbol extraction ---

def _node_first_identifier(node: Node) -> str:
    for child in node.children:
        if child.type == "identifier":
            return child.text.decode()
    return ""


def _signature_line(node: Node, lines: list[str]) -> str | None:
    ln = node.start_point[0]
    return lines[ln].strip() if ln < len(lines) else None


def _extract_symbols(root: Node, lines: list[str]) -> list[ParsedSymbol]:
    symbols: list[ParsedSymbol] = []
    for node in root.children:
        if node.type == "function_definition":
            name = _node_first_identifier(node)
            symbols.append(ParsedSymbol(
                name=name,
                qualified_name=name,
                kind="function",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_signature_line(node, lines),
            ))
        elif node.type == "class_definition":
            class_name = _node_first_identifier(node)
            symbols.append(ParsedSymbol(
                name=class_name,
                qualified_name=class_name,
                kind="class",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_signature_line(node, lines),
            ))
            block = next((c for c in node.children if c.type == "block"), None)
            if block:
                for child in block.children:
                    if child.type == "function_definition":
                        method_name = _node_first_identifier(child)
                        symbols.append(ParsedSymbol(
                            name=method_name,
                            qualified_name=f"{class_name}.{method_name}",
                            kind="method",
                            start_line=child.start_point[0] + 1,
                            end_line=child.end_point[0] + 1,
                            signature=_signature_line(child, lines),
                        ))
    return symbols


# --- reference extraction ---

def _extract_references(root: Node) -> list[ParsedReference]:
    refs: list[ParsedReference] = []
    _collect_refs(root, refs)
    return refs


def _collect_refs(node: Node, refs: list[ParsedReference]) -> None:
    t = node.type
    if t == "import_statement":
        _refs_from_import(node, refs)
        return
    if t == "import_from_statement":
        _refs_from_import_from(node, refs)
        return
    if t == "call":
        _refs_from_call(node, refs)
        # recurse into argument list so nested calls are captured
        for child in node.children:
            if child.type == "argument_list":
                _collect_refs(child, refs)
        return
    for child in node.children:
        _collect_refs(child, refs)


def _refs_from_import(node: Node, refs: list[ParsedReference]) -> None:
    line = node.start_point[0] + 1
    for child in node.children:
        if child.type == "dotted_name":
            refs.append(ParsedReference(symbol_name=child.text.decode(), line_number=line))
        elif child.type == "aliased_import":
            dotted = next((c for c in child.children if c.type == "dotted_name"), None)
            if dotted:
                refs.append(ParsedReference(symbol_name=dotted.text.decode(), line_number=line))


def _refs_from_import_from(node: Node, refs: list[ParsedReference]) -> None:
    line = node.start_point[0] + 1
    past_import = False
    for child in node.children:
        if child.type == "import":
            past_import = True
            continue
        if not past_import:
            continue
        if child.type == "dotted_name":
            refs.append(ParsedReference(symbol_name=child.text.decode(), line_number=line))
        elif child.type == "aliased_import":
            dotted = next((c for c in child.children if c.type == "dotted_name"), None)
            if dotted:
                refs.append(ParsedReference(symbol_name=dotted.text.decode(), line_number=line))


def _refs_from_call(node: Node, refs: list[ParsedReference]) -> None:
    # Attribute calls stored by final identifier only (e.g. client.save() → "save"). Step 13 resolver must handle ambiguity.
    func = node.children[0] if node.children else None
    if func is None:
        return
    if func.type == "identifier":
        refs.append(ParsedReference(
            symbol_name=func.text.decode(),
            line_number=node.start_point[0] + 1,
        ))
    elif func.type == "attribute":
        attr = next((c for c in reversed(func.children) if c.type == "identifier"), None)
        if attr:
            refs.append(ParsedReference(
                symbol_name=attr.text.decode(),
                line_number=node.start_point[0] + 1,
            ))
