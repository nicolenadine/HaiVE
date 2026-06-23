import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from haive.adapters.vcs.github import GitHubVCSAdapter


def _fake_settings(**overrides):
    s = MagicMock()
    s.github_token = overrides.get("github_token", "ghp_test")
    s.github_repo = overrides.get("github_repo", "owner/repo")
    return s


def _make_adapter() -> GitHubVCSAdapter:
    adapter = GitHubVCSAdapter.__new__(GitHubVCSAdapter)
    adapter._token = "ghp_test"
    adapter._gh = MagicMock()
    adapter._repo_obj = MagicMock()
    adapter._graphql = MagicMock()
    return adapter


# ---------------------------------------------------------------------------
# TestVCSStartupValidation
# ---------------------------------------------------------------------------

class TestVCSStartupValidation:
    def test_missing_token_raises_value_error(self):
        with patch("haive.adapters.vcs.github.github.Github"):
            with pytest.raises(ValueError, match="GITHUB_TOKEN"):
                GitHubVCSAdapter(_fake_settings(github_token=None))

    def test_missing_repo_raises_value_error(self):
        with patch("haive.adapters.vcs.github.github.Github"):
            with pytest.raises(ValueError, match="GITHUB_REPO"):
                GitHubVCSAdapter(_fake_settings(github_repo=None))

    def test_malformed_repo_raises_value_error(self):
        with patch("haive.adapters.vcs.github.github.Github"):
            with pytest.raises(ValueError, match="owner/repo"):
                GitHubVCSAdapter(_fake_settings(github_repo="just-a-name"))


# ---------------------------------------------------------------------------
# TestCreateBranch
# ---------------------------------------------------------------------------

class TestCreateBranch:
    def test_creates_ref_from_base_sha(self):
        adapter = _make_adapter()
        source = MagicMock()
        source.commit.sha = "abc123"
        adapter._repo_obj.get_branch.return_value = source

        adapter.create_branch("haive/project-1", "main")

        adapter._repo_obj.get_branch.assert_called_once_with("main")
        adapter._repo_obj.create_git_ref.assert_called_once_with(
            ref="refs/heads/haive/project-1",
            sha="abc123",
        )


# ---------------------------------------------------------------------------
# TestPushCommits
# ---------------------------------------------------------------------------

class TestPushCommits:
    def test_runs_add_commit_push_in_order(self):
        adapter = _make_adapter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.push_commits("haive/project-1", ["src/foo.py", "src/bar.py"], "Add files")

        assert mock_run.call_count == 3
        calls = mock_run.call_args_list
        assert calls[0] == call(
            ["git", "add", "--", "src/foo.py", "src/bar.py"], check=True, capture_output=True
        )
        assert calls[1] == call(["git", "commit", "-m", "Add files"], check=True, capture_output=True)
        assert calls[2] == call(
            ["git", "push", "origin", "haive/project-1"], check=True, capture_output=True
        )

    def test_raises_runtime_error_on_git_failure(self):
        adapter = _make_adapter()
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git add", stderr=b"error")
            with pytest.raises(RuntimeError, match="git command failed"):
                adapter.push_commits("main", ["file.py"], "msg")


# ---------------------------------------------------------------------------
# TestCreatePR
# ---------------------------------------------------------------------------

class TestCreatePR:
    def test_returns_pr_number_as_string(self):
        adapter = _make_adapter()
        pr = MagicMock()
        pr.number = 7
        adapter._repo_obj.create_pull.return_value = pr

        result = adapter.create_pr("My PR", "Body text", "feature", "main")

        assert result == "7"
        adapter._repo_obj.create_pull.assert_called_once_with(
            title="My PR",
            body="Body text",
            head="feature",
            base="main",
        )


# ---------------------------------------------------------------------------
# TestMergePR
# ---------------------------------------------------------------------------

class TestMergePR:
    def test_enables_automerge_via_graphql(self):
        adapter = _make_adapter()
        pr = MagicMock()
        pr.raw_data = {"node_id": "PR_node7"}
        adapter._repo_obj.get_pull.return_value = pr
        adapter._graphql.return_value = {
            "enablePullRequestAutoMerge": {"pullRequest": {"number": 7}}
        }

        adapter.merge_pr("7")

        adapter._repo_obj.get_pull.assert_called_once_with(7)
        call_vars = adapter._graphql.call_args[0][1]
        assert call_vars["pullRequestId"] == "PR_node7"

    def test_falls_back_to_direct_merge_if_automerge_unavailable(self):
        adapter = _make_adapter()
        pr = MagicMock()
        pr.raw_data = {"node_id": "PR_node7"}
        adapter._repo_obj.get_pull.return_value = pr
        adapter._graphql.side_effect = RuntimeError("auto-merge not enabled on repo")

        adapter.merge_pr("7")

        pr.merge.assert_called_once_with(merge_method="squash")


# ---------------------------------------------------------------------------
# TestAddPRComment
# ---------------------------------------------------------------------------

class TestAddPRComment:
    def test_creates_issue_comment_on_pr(self):
        adapter = _make_adapter()

        adapter.add_pr_comment("7", "LGTM!")

        adapter._repo_obj.get_pull.assert_called_once_with(7)
        adapter._repo_obj.get_pull.return_value.create_issue_comment.assert_called_once_with("LGTM!")


# ---------------------------------------------------------------------------
# TestCreateProjectPR
# ---------------------------------------------------------------------------

class TestCreateProjectPR:
    def test_delegates_to_create_pr(self):
        adapter = _make_adapter()
        pr = MagicMock()
        pr.number = 5
        adapter._repo_obj.create_pull.return_value = pr

        result = adapter.create_project_pr("haive/project-1", "main", "Project PR", "Summary")

        assert result == "5"
        adapter._repo_obj.create_pull.assert_called_once_with(
            title="Project PR",
            body="Summary",
            head="haive/project-1",
            base="main",
        )


# ---------------------------------------------------------------------------
# TestVCSAdapterBoundaries
# ---------------------------------------------------------------------------

class TestVCSAdapterBoundaries:
    def test_no_component_outside_adapters_imports_pygithub(self):
        import sys
        for mod_name, mod in list(sys.modules.items()):
            if mod_name.startswith("haive.") and not mod_name.startswith("haive.adapters"):
                source = getattr(mod, "__file__", "") or ""
                if source.endswith(".py"):
                    with open(source) as f:
                        content = f.read()
                    assert "import github" not in content and "from github" not in content, \
                        f"{mod_name} must not import PyGithub"
