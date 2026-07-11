from __future__ import annotations

from haive.execution.dependency_approval import DependencyApprovalGate

_OLD_PYPROJECT = """\
[project]
name = "demo"
dependencies = ["requests>=2.0"]
"""

_NEW_PYPROJECT_ADDS_UNAPPROVED = """\
[project]
name = "demo"
dependencies = ["requests>=2.0", "sketchy-pkg"]
"""

_NEW_PYPROJECT_ADDS_APPROVED = """\
[project]
name = "demo"
dependencies = ["requests>=2.0", "pydantic"]
"""


def _write_pyproject(root, content: str) -> None:
    (root / "pyproject.toml").write_text(content)


def _write_allowlist(root, names: list[str]) -> None:
    haive_dir = root / ".haive"
    haive_dir.mkdir(parents=True, exist_ok=True)
    (haive_dir / "allowed_dependencies.txt").write_text("\n".join(names) + "\n")


class TestNoManifestChange:
    def test_passes_when_pyproject_not_in_changed_paths(self, tmp_path):
        _write_pyproject(tmp_path, _NEW_PYPROJECT_ADDS_UNAPPROVED)
        gate = DependencyApprovalGate(str(tmp_path))
        result = gate.check(["some_other_file.py"], {})
        assert result.approved is True

    def test_passes_when_no_new_dependency_added(self, tmp_path):
        _write_pyproject(tmp_path, _OLD_PYPROJECT)
        gate = DependencyApprovalGate(str(tmp_path))
        result = gate.check(["pyproject.toml"], {"pyproject.toml": _OLD_PYPROJECT})
        assert result.approved is True


class TestMissingAllowlist:
    def test_skips_gate_but_warns_when_no_allowlist_file(self, tmp_path):
        _write_pyproject(tmp_path, _NEW_PYPROJECT_ADDS_UNAPPROVED)
        gate = DependencyApprovalGate(str(tmp_path))
        result = gate.check(["pyproject.toml"], {"pyproject.toml": _OLD_PYPROJECT})
        assert result.approved is True
        assert "sketchy-pkg" in result.warning
        assert ".haive/allowed_dependencies.txt" in result.warning


class TestWithAllowlist:
    def test_blocks_unapproved_new_dependency(self, tmp_path):
        _write_pyproject(tmp_path, _NEW_PYPROJECT_ADDS_UNAPPROVED)
        _write_allowlist(tmp_path, ["requests", "pydantic"])
        gate = DependencyApprovalGate(str(tmp_path))
        result = gate.check(["pyproject.toml"], {"pyproject.toml": _OLD_PYPROJECT})
        assert result.approved is False
        assert result.unapproved_dependencies == ["sketchy-pkg"]

    def test_allows_approved_new_dependency(self, tmp_path):
        _write_pyproject(tmp_path, _NEW_PYPROJECT_ADDS_APPROVED)
        _write_allowlist(tmp_path, ["requests", "pydantic"])
        gate = DependencyApprovalGate(str(tmp_path))
        result = gate.check(["pyproject.toml"], {"pyproject.toml": _OLD_PYPROJECT})
        assert result.approved is True
        assert result.warning == ""

    def test_allowlist_comments_and_blank_lines_ignored(self, tmp_path):
        _write_pyproject(tmp_path, _NEW_PYPROJECT_ADDS_APPROVED)
        allow_file = tmp_path / ".haive" / "allowed_dependencies.txt"
        allow_file.parent.mkdir(parents=True, exist_ok=True)
        allow_file.write_text("# core deps\nrequests\n\npydantic\n")
        gate = DependencyApprovalGate(str(tmp_path))
        result = gate.check(["pyproject.toml"], {"pyproject.toml": _OLD_PYPROJECT})
        assert result.approved is True

    def test_first_scaffold_with_no_prior_content_checks_all_deps(self, tmp_path):
        # No original_contents entry at all -- pyproject.toml is brand new.
        _write_pyproject(tmp_path, _NEW_PYPROJECT_ADDS_UNAPPROVED)
        _write_allowlist(tmp_path, ["requests"])
        gate = DependencyApprovalGate(str(tmp_path))
        result = gate.check(["pyproject.toml"], {})
        assert result.approved is False
        assert result.unapproved_dependencies == ["sketchy-pkg"]


class TestDisabled:
    def test_disabled_gate_always_passes(self, tmp_path):
        _write_pyproject(tmp_path, _NEW_PYPROJECT_ADDS_UNAPPROVED)
        _write_allowlist(tmp_path, ["requests"])
        gate = DependencyApprovalGate(str(tmp_path), enabled=False)
        result = gate.check(["pyproject.toml"], {"pyproject.toml": _OLD_PYPROJECT})
        assert result.approved is True
        assert result.warning == ""
