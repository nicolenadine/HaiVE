from __future__ import annotations

import ast
import os
import re

# Matches a 2-space indented symbol sub-entry: "  name (kind) — start-end[ — description]"
# Capturing (unlike AgentMdValidator's version) so the description suffix can be preserved verbatim.
_SYMBOL_ENTRY_RE = re.compile(r"^  (\S+) \((\w+)\) — (\d+)-(\d+)( — .+)?$")

# Kinds whose line ranges are worth correcting: multi-line spans an LLM can miscount.
# "constant" entries are typically single-line and out of scope for this pass.
_CORRECTABLE_KINDS = {"class", "function", "method"}


class _PySymbol:
    __slots__ = ("name", "kind", "start", "end")

    def __init__(self, name: str, kind: str, start: int, end: int) -> None:
        self.name = name
        self.kind = kind
        self.start = start
        self.end = end


def _collect_python_symbols(source: str) -> list[_PySymbol]:
    """Return every class/function/method definition in source via ast.

    Exact, not estimated — node.lineno/end_lineno come from the same parser
    that runs the code, so there is nothing to get wrong here.
    """
    tree = ast.parse(source)
    symbols: list[_PySymbol] = []

    def visit(node: ast.AST, in_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                symbols.append(_PySymbol(child.name, "class", child.lineno, child.end_lineno))
                visit(child, in_class=True)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if in_class else "function"
                symbols.append(_PySymbol(child.name, kind, child.lineno, child.end_lineno))
                visit(child, in_class=False)
            else:
                visit(child, in_class=in_class)

    visit(tree, in_class=False)
    return symbols


def _best_match(
    symbols: list[_PySymbol], name: str, kind: str, guessed_start: int
) -> _PySymbol | None:
    """Pick the real symbol matching `name`, disambiguating duplicates.

    A name isn't always unique in a file (e.g. __init__ in every class). The
    LLM is bad at exact line counting but generally isn't looking at the
    wrong part of the file — so among same-named candidates, prefer a kind
    match, then the one closest to the LLM's original (wrong) guess.
    """
    candidates = [s for s in symbols if s.name == name]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda s: (s.kind != kind, abs(s.start - guessed_start)))


def _load_symbols(dir_path: str, filename: str) -> list[_PySymbol] | None:
    path = os.path.join(dir_path, filename)
    try:
        source = open(path, encoding="utf-8").read()
    except OSError:
        return None
    try:
        return _collect_python_symbols(source)
    except SyntaxError:
        return None


def correct_line_ranges(content: str, dir_path: str) -> str:
    """Correct symbol start-end line numbers in already-valid agent.md content.

    Uses each referenced Python file's real ast — deterministic, no LLM
    involved — rather than trusting the generation agent's estimate. Entries
    for non-Python files, non-correctable kinds, or symbol names that can't
    be matched in the real source are left unchanged rather than guessed at.
    """
    lines = content.splitlines()
    corrected: list[str] = []
    current_file: str | None = None
    symbol_cache: dict[str, list[_PySymbol] | None] = {}

    for line in lines:
        if not line.startswith("  ") and " — " in line:
            current_file = line.split(" — ", 1)[0].strip()
            corrected.append(line)
            continue

        match = _SYMBOL_ENTRY_RE.match(line)
        if not match or current_file is None or not current_file.endswith(".py"):
            corrected.append(line)
            continue

        name, kind, start_str = match.group(1), match.group(2), match.group(3)
        suffix = match.group(5) or ""

        if kind not in _CORRECTABLE_KINDS:
            corrected.append(line)
            continue

        if current_file not in symbol_cache:
            symbol_cache[current_file] = _load_symbols(dir_path, current_file)
        symbols = symbol_cache[current_file]

        if symbols is None:
            corrected.append(line)
            continue

        best = _best_match(symbols, name, kind, int(start_str))
        if best is None:
            corrected.append(line)
            continue

        corrected.append(f"  {name} ({kind}) — {best.start}-{best.end}{suffix}")

    result = "\n".join(corrected)
    if content.endswith("\n"):
        result += "\n"
    return result
