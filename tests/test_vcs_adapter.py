import subprocess
from unittest.mock import MagicMock, call, patch

import github
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

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.create_branch("haive/project-1", "main")

        adapter._repo_obj.get_branch.assert_called_once_with("main")
        adapter._repo_obj.create_git_ref.assert_called_once_with(
            ref="refs/heads/haive/project-1",
            sha="abc123",
        )

    def test_checks_out_local_branch_after_remote_ref(self):
        adapter = _make_adapter()
        source = MagicMock()
        source.commit.sha = "abc123"
        adapter._repo_obj.get_branch.return_value = source

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.create_branch("haive/project-1", "main")

        mock_run.assert_called_once_with(
            ["git", "checkout", "-B", "haive/project-1", "main"],
            check=True, capture_output=True,
        )

    def test_reuses_branch_that_already_exists_remotely(self):
        adapter = _make_adapter()
        source = MagicMock()
        source.commit.sha = "abc123"
        adapter._repo_obj.get_branch.return_value = source
        adapter._repo_obj.create_git_ref.side_effect = github.GithubException(422, "exists", None)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.create_branch("haive/project-1", "main")

        mock_run.assert_called_once_with(
            ["git", "checkout", "-B", "haive/project-1", "main"],
            check=True, capture_output=True,
        )

    def test_local_checkout_failure_raises_runtime_error(self):
        adapter = _make_adapter()
        source = MagicMock()
        source.commit.sha = "abc123"
        adapter._repo_obj.get_branch.return_value = source

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git checkout", stderr=b"error")
            with pytest.raises(RuntimeError, match="git command failed"):
                adapter.create_branch("haive/project-1", "main")


# ---------------------------------------------------------------------------
# TestCheckoutBranch
# ---------------------------------------------------------------------------

class TestCheckoutBranch:
    def test_runs_checkout_then_pull(self):
        adapter = _make_adapter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.checkout_branch("main")

        assert mock_run.call_count == 2
        calls = mock_run.call_args_list
        assert calls[0] == call(["git", "checkout", "main"], check=True, capture_output=True)
        assert calls[1] == call(["git", "pull", "origin", "main"], check=True, capture_output=True)

    def test_raises_runtime_error_on_git_failure(self):
        adapter = _make_adapter()
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git checkout", stderr=b"error")
            with pytest.raises(RuntimeError, match="git command failed"):
                adapter.checkout_branch("main")


# ---------------------------------------------------------------------------
# TestPushCommits
# ---------------------------------------------------------------------------

class TestPushCommits:
    def test_runs_reset_add_commit_push_in_order(self):
        adapter = _make_adapter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.push_commits("haive/project-1", ["src/foo.py", "src/bar.py"], "Add files")

        assert mock_run.call_count == 4
        calls = mock_run.call_args_list
        assert calls[0] == call(["git", "reset"], check=True, capture_output=True)
        assert calls[1] == call(
            ["git", "add", "--", "src/foo.py", "src/bar.py"], check=True, capture_output=True
        )
        assert calls[2] == call(["git", "commit", "-m", "Add files"], check=True, capture_output=True)
        assert calls[3] == call(
            ["git", "push", "origin", "haive/project-1"], check=True, capture_output=True
        )

    def test_reset_runs_before_staging_even_with_empty_changed_files(self):
        # If something else was already staged before this call (e.g. leftover
        # index state from unrelated prior activity), the reset must ensure the
        # commit only ever contains exactly changed_files, not that stale content.
        adapter = _make_adapter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.push_commits("haive/project-1", [], "Empty edit set")

        reset_call, add_call = mock_run.call_args_list[0], mock_run.call_args_list[1]
        assert reset_call == call(["git", "reset"], check=True, capture_output=True)
        assert add_call == call(["git", "add", "--"], check=True, capture_output=True)

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

    def test_github_error_raises_runtime_error(self):
        adapter = _make_adapter()
        adapter._repo_obj.create_pull.side_effect = github.GithubException(
            422, {"message": "No commits between main and main"}, None
        )

        with pytest.raises(RuntimeError, match="No commits between main and main"):
            adapter.create_pr("My PR", "Body text", "main", "main")


# ---------------------------------------------------------------------------
# TestMergePR
# ---------------------------------------------------------------------------

class TestMergePR:
    def test_merges_directly_when_pr_is_immediately_mergeable(self):
        adapter = _make_adapter()
        pr = MagicMock()
        pr.raw_data = {"node_id": "PR_node7"}
        adapter._repo_obj.get_pull.return_value = pr

        adapter.merge_pr("7")

        adapter._repo_obj.get_pull.assert_called_once_with(7)
        pr.merge.assert_called_once_with(merge_method="squash")
        adapter._graphql.assert_not_called()

    def test_falls_back_to_automerge_via_graphql_when_direct_merge_fails(self):
        adapter = _make_adapter()
        pr = MagicMock()
        pr.raw_data = {"node_id": "PR_node7"}
        pr.merge.side_effect = github.GithubException(405, {"message": "Pull Request is not mergeable"}, None)
        adapter._repo_obj.get_pull.return_value = pr
        adapter._graphql.return_value = {
            "enablePullRequestAutoMerge": {"pullRequest": {"number": 7}}
        }

        adapter.merge_pr("7")

        call_vars = adapter._graphql.call_args[0][1]
        assert call_vars["pullRequestId"] == "PR_node7"

    def test_propagates_combined_error_if_both_merge_and_automerge_fail(self):
        adapter = _make_adapter()
        pr = MagicMock()
        pr.raw_data = {"node_id": "PR_node7"}
        pr.merge.side_effect = github.GithubException(405, {"message": "Pull Request is not mergeable"}, None)
        adapter._repo_obj.get_pull.return_value = pr
        adapter._graphql.side_effect = RuntimeError("auto-merge not available")

        with pytest.raises(RuntimeError, match="auto-merge not available"):
            adapter.merge_pr("7")


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
# TestIsPRMerged
# ---------------------------------------------------------------------------

class TestIsPRMerged:
    def test_returns_true_when_merged(self):
        adapter = _make_adapter()
        pr = MagicMock()
        pr.merged = True
        adapter._repo_obj.get_pull.return_value = pr

        assert adapter.is_pr_merged("7") is True
        adapter._repo_obj.get_pull.assert_called_once_with(7)

    def test_returns_false_when_not_merged(self):
        adapter = _make_adapter()
        pr = MagicMock()
        pr.merged = False
        adapter._repo_obj.get_pull.return_value = pr

        assert adapter.is_pr_merged("7") is False


# ---------------------------------------------------------------------------
# TestListTaskBranches
# ---------------------------------------------------------------------------

class TestListTaskBranches:
    def test_filters_by_prefix(self):
        adapter = _make_adapter()
        b1, b2, b3 = MagicMock(), MagicMock(), MagicMock()
        b1.name = "haive/task-1"
        b2.name = "haive/task-2"
        b3.name = "main"
        adapter._repo_obj.get_branches.return_value = [b1, b2, b3]

        result = adapter.list_task_branches("haive/task-")

        assert result == ["haive/task-1", "haive/task-2"]


# ---------------------------------------------------------------------------
# TestFindPRForBranch
# ---------------------------------------------------------------------------

class TestFindPRForBranch:
    def test_returns_pr_number_and_merged_state(self):
        adapter = _make_adapter()
        adapter._repo_obj.owner.login = "owner"
        pr = MagicMock()
        pr.number = 9
        pr.merged = True
        adapter._repo_obj.get_pulls.return_value = [pr]

        result = adapter.find_pr_for_branch("haive/task-9")

        assert result == ("9", True)
        adapter._repo_obj.get_pulls.assert_called_once_with(state="all", head="owner:haive/task-9")

    def test_returns_unmerged_state(self):
        adapter = _make_adapter()
        adapter._repo_obj.owner.login = "owner"
        pr = MagicMock()
        pr.number = 9
        pr.merged = False
        adapter._repo_obj.get_pulls.return_value = [pr]

        result = adapter.find_pr_for_branch("haive/task-9")

        assert result == ("9", False)

    def test_returns_none_when_no_pr_found(self):
        adapter = _make_adapter()
        adapter._repo_obj.owner.login = "owner"
        adapter._repo_obj.get_pulls.return_value = []

        assert adapter.find_pr_for_branch("haive/task-9") is None


# ---------------------------------------------------------------------------
# TestDeleteBranch
# ---------------------------------------------------------------------------

class TestDeleteBranch:
    def test_deletes_git_ref(self):
        adapter = _make_adapter()
        ref = MagicMock()
        adapter._repo_obj.get_git_ref.return_value = ref

        adapter.delete_branch("haive/task-9")

        adapter._repo_obj.get_git_ref.assert_called_once_with("heads/haive/task-9")
        ref.delete.assert_called_once()


# ---------------------------------------------------------------------------
# TestEnsureBranch
# ---------------------------------------------------------------------------

class TestEnsureBranch:
    def test_syncs_existing_branch_instead_of_recreating(self):
        adapter = _make_adapter()
        adapter._repo_obj.get_branch.return_value = MagicMock()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.ensure_branch("haive/project-12", "main")

        adapter._repo_obj.get_branch.assert_called_once_with("haive/project-12")
        # checkout_branch's calls: checkout then pull — never create_git_ref
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0] == call(
            ["git", "checkout", "haive/project-12"], check=True, capture_output=True
        )
        adapter._repo_obj.create_git_ref.assert_not_called()

    def test_creates_branch_when_missing(self):
        adapter = _make_adapter()
        adapter._repo_obj.get_branch.side_effect = [
            github.GithubException(404, {"message": "Not Found"}, None),
            MagicMock(commit=MagicMock(sha="abc123")),  # create_branch's own get_branch(base) call
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            adapter.ensure_branch("haive/project-12", "main")

        adapter._repo_obj.create_git_ref.assert_called_once_with(
            ref="refs/heads/haive/project-12", sha="abc123",
        )

    def test_non_404_error_propagates(self):
        adapter = _make_adapter()
        adapter._repo_obj.get_branch.side_effect = github.GithubException(
            500, {"message": "Server Error"}, None
        )

        with pytest.raises(github.GithubException):
            adapter.ensure_branch("haive/project-12", "main")


# ---------------------------------------------------------------------------
# TestBranchHasNewCommits
# ---------------------------------------------------------------------------

class TestBranchHasNewCommits:
    def test_true_when_ahead(self):
        adapter = _make_adapter()
        comparison = MagicMock(ahead_by=3)
        adapter._repo_obj.compare.return_value = comparison

        assert adapter.branch_has_new_commits("main", "haive/project-12") is True
        adapter._repo_obj.compare.assert_called_once_with("main", "haive/project-12")

    def test_false_when_not_ahead(self):
        adapter = _make_adapter()
        adapter._repo_obj.compare.return_value = MagicMock(ahead_by=0)

        assert adapter.branch_has_new_commits("main", "haive/project-12") is False


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
