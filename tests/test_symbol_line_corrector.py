from __future__ import annotations

from haive.discovery.symbol_line_corrector import correct_line_ranges


def _write(tmp_path, filename: str, source: str) -> None:
    (tmp_path / filename).write_text(source)


class TestCorrectLineRanges:
    def test_corrects_wrong_function_range(self, tmp_path):
        source = "\n".join(["# padding"] * 10 + ["def real_function():", "    pass"])
        _write(tmp_path, "task.py", source)
        content = (
            "## Files\n\n"
            "task.py — Task module\n"
            "  real_function (function) — 1-2 — does a thing\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "real_function (function) — 11-12 — does a thing" in result

    def test_corrects_wrong_class_range(self, tmp_path):
        source = "\n".join(["# padding"] * 5 + ["class Task:", "    def method(self):", "        pass"])
        _write(tmp_path, "task.py", source)
        content = (
            "## Files\n\n"
            "task.py — Task module\n"
            "  Task (class) — 1-1 — domain model\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "Task (class) — 6-8 — domain model" in result

    def test_nested_method_gets_method_kind_from_ast_not_from_entry(self, tmp_path):
        source = "\n".join(["class Task:", "    def method(self):", "        pass"])
        _write(tmp_path, "task.py", source)
        content = (
            "## Files\n\n"
            "task.py — Task module\n"
            "  method (method) — 99-99 — does a thing\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "method (method) — 2-3 — does a thing" in result

    def test_disambiguates_duplicate_names_by_nearest_guess(self, tmp_path):
        source = "\n".join(
            [
                "class First:",
                "    def __init__(self):",
                "        pass",
                "",
                "class Second:",
                "    def __init__(self):",
                "        pass",
            ]
        )
        _write(tmp_path, "task.py", source)
        # Guessed near line 6 (Second.__init__) -- should pick the real line-6 one, not line 2.
        content = (
            "## Files\n\n"
            "task.py — Task module\n"
            "  __init__ (method) — 5-5 — constructor\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "__init__ (method) — 6-7 — constructor" in result

    def test_unmatched_symbol_name_left_unchanged(self, tmp_path):
        _write(tmp_path, "task.py", "class Task:\n    pass\n")
        content = (
            "## Files\n\n"
            "task.py — Task module\n"
            "  nonexistent_function (function) — 1-2 — hallucinated\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "nonexistent_function (function) — 1-2 — hallucinated" in result

    def test_non_python_file_left_unchanged(self, tmp_path):
        _write(tmp_path, "notes.md", "# Notes\n")
        content = (
            "## Files\n\n"
            "notes.md — Notes file\n"
            "  Section (constant) — 1-5 — a section\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "Section (constant) — 1-5 — a section" in result

    def test_constant_kind_left_unchanged(self, tmp_path):
        _write(tmp_path, "task.py", "\n".join(["# padding"] * 10 + ["MAX = 3"]))
        content = (
            "## Files\n\n"
            "task.py — Task module\n"
            "  MAX (constant) — 1-1 — a constant\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "MAX (constant) — 1-1 — a constant" in result

    def test_missing_source_file_left_unchanged(self, tmp_path):
        content = (
            "## Files\n\n"
            "missing.py — Missing file\n"
            "  fn (function) — 1-2 — a function\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "fn (function) — 1-2 — a function" in result

    def test_unparsable_source_file_left_unchanged(self, tmp_path):
        _write(tmp_path, "broken.py", "def broken(:\n")
        content = (
            "## Files\n\n"
            "broken.py — Broken file\n"
            "  broken (function) — 1-1 — a function\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "broken (function) — 1-1 — a function" in result

    def test_entry_without_description_suffix_is_preserved(self, tmp_path):
        source = "\n".join(["# padding"] * 3 + ["def real_function():", "    pass"])
        _write(tmp_path, "task.py", source)
        content = (
            "## Files\n\n"
            "task.py — Task module\n"
            "  real_function (function) — 1-1\n"
        )

        result = correct_line_ranges(content, str(tmp_path))

        assert "real_function (function) — 4-5" in result
        assert "real_function (function) — 4-5 —" not in result
