from __future__ import annotations

from typing import runtime_checkable

import pytest

from haive.repomap.language_parser import (
    LanguageParser,
    ParsedFile,
    ParsedSymbol,
    PythonParser,
)

_CLASS_AND_METHODS = """\
import os
from pathlib import Path

class Widget:
    def render(self):
        os.getcwd()

    def destroy(self):
        pass
"""

_TOP_FUNCTIONS = """\
def add(x, y):
    return x + y

def subtract(x, y):
    return x - y
"""


class TestPythonParserSymbols:
    def _parse(self, src: str) -> ParsedFile:
        return PythonParser().parse_file("test.py", src)

    def test_one_class_two_methods_returns_three_symbols(self):
        result = self._parse(_CLASS_AND_METHODS)
        kinds = [(s.qualified_name, s.kind) for s in result.symbols]
        assert ("Widget", "class") in kinds
        assert ("Widget.render", "method") in kinds
        assert ("Widget.destroy", "method") in kinds
        assert len([s for s in result.symbols if s.kind in ("class", "method")]) == 3

    def test_top_level_functions_have_kind_function(self):
        result = self._parse(_TOP_FUNCTIONS)
        assert all(s.kind == "function" for s in result.symbols)
        assert {s.name for s in result.symbols} == {"add", "subtract"}

    def test_method_qualified_name_prefixed_with_class(self):
        result = self._parse(_CLASS_AND_METHODS)
        method = next(s for s in result.symbols if s.name == "render")
        assert method.qualified_name == "Widget.render"
        assert method.kind == "method"

    def test_start_and_end_lines_are_one_indexed(self):
        result = self._parse(_TOP_FUNCTIONS)
        fn = next(s for s in result.symbols if s.name == "add")
        assert fn.start_line == 1
        assert fn.end_line >= 1

    def test_signature_contains_def_line(self):
        result = self._parse(_TOP_FUNCTIONS)
        fn = next(s for s in result.symbols if s.name == "add")
        assert fn.signature is not None
        assert "def add" in fn.signature

    def test_empty_file_has_no_symbols(self):
        result = self._parse("")
        assert result.symbols == []


class TestPythonParserReferences:
    def _parse(self, src: str) -> ParsedFile:
        return PythonParser().parse_file("test.py", src)

    def test_import_statement_captured_as_reference(self):
        result = self._parse("import os\n")
        names = {r.symbol_name for r in result.references}
        assert "os" in names

    def test_from_import_captured_as_reference(self):
        result = self._parse("from pathlib import Path\n")
        names = {r.symbol_name for r in result.references}
        assert "Path" in names

    def test_multiple_from_imports_all_captured(self):
        result = self._parse("from os.path import join, exists\n")
        names = {r.symbol_name for r in result.references}
        assert "join" in names
        assert "exists" in names

    def test_function_call_captured_as_reference(self):
        result = self._parse("def f():\n    helper()\n")
        names = {r.symbol_name for r in result.references}
        assert "helper" in names

    def test_reference_line_number_is_one_indexed(self):
        result = self._parse("import os\n")
        ref = next(r for r in result.references if r.symbol_name == "os")
        assert ref.line_number == 1


class TestPythonParserContentHash:
    def test_hash_is_stable_for_same_content(self):
        p = PythonParser()
        h1 = p.parse_file("a.py", "x = 1\n").content_hash
        h2 = p.parse_file("a.py", "x = 1\n").content_hash
        assert h1 == h2

    def test_hash_differs_for_different_content(self):
        p = PythonParser()
        h1 = p.parse_file("a.py", "x = 1\n").content_hash
        h2 = p.parse_file("a.py", "x = 2\n").content_hash
        assert h1 != h2


class TestPythonParserV1Scope:
    """Document extraction boundaries for v1. Nested and class-in-class cases are deferred."""

    def test_async_functions_are_captured(self):
        # tree-sitter-python emits function_definition for both sync and async
        result = PythonParser().parse_file("t.py", "async def handler(): pass\n")
        assert any(s.name == "handler" for s in result.symbols)

    def test_nested_functions_are_not_extracted(self):
        result = PythonParser().parse_file("t.py", "def outer():\n    def inner(): pass\n")
        names = {s.name for s in result.symbols}
        assert "inner" not in names

    def test_nested_classes_are_not_extracted(self):
        src = "class Outer:\n    class Inner:\n        def method(self): pass\n"
        result = PythonParser().parse_file("t.py", src)
        names = {s.name for s in result.symbols}
        assert "Inner" not in names
        assert "method" not in names


class TestLanguageParserProtocol:
    def test_python_parser_satisfies_protocol_without_inheriting(self):
        assert not issubclass(PythonParser, object.__class__)
        # PythonParser must not subclass LanguageParser
        assert LanguageParser not in PythonParser.__mro__

    def test_python_parser_has_required_protocol_attributes(self):
        p = PythonParser()
        assert hasattr(p, "extensions")
        assert hasattr(p, "language")
        assert hasattr(p, "parse_file")
        assert callable(p.parse_file)
