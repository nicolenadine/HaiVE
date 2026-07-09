from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import github
import pytest

from haive.adapters.pm.github import GitHubPMAdapter, _parse_checkpoint
from haive.models.enums import AgentRole, Complexity, TaskStatus

_FIELD_IDS: dict[str, str] = {
    "Status":                    "F_status",
    "haive_agent_role":          "F_agent_role",
    "haive_complexity":          "F_complexity",
    "haive_depends_on":          "F_depends_on",
    "haive_lineage_depth":       "F_lineage_depth",
    "haive_recovery_for":        "F_recovery_for",
    "haive_acceptance_criteria": "F_acceptance_criteria",
}

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_RESOLVE_RESPONSE = {
    "repository": {
        "owner": {
            "projectV2": {"id": "PVT_kgTest"}
        }
    }
}

_ALL_FIELDS_RESPONSE = {
    "node": {
        "fields": {
            "nodes": [
                {"name": "haive_agent_role"},
                {"name": "haive_complexity"},
                {"name": "haive_depends_on"},
                {"name": "haive_lineage_depth"},
                {"name": "haive_recovery_for"},
                {"name": "haive_acceptance_criteria"},
                {"name": "Status"},
                {"name": "Title"},
            ]
        }
    }
}

_CONSTRUCTOR_RESPONSES = [_RESOLVE_RESPONSE, _ALL_FIELDS_RESPONSE]


def _fake_settings(**overrides):
    s = MagicMock()
    s.github_token = overrides.get("github_token", "ghp_test")
    s.github_repo = overrides.get("github_repo", "owner/repo")
    s.github_project_id = overrides.get("github_project_id", 7)
    return s


def _make_adapter() -> GitHubPMAdapter:
    """Create a pre-wired adapter bypassing __init__ for non-startup tests."""
    adapter = GitHubPMAdapter.__new__(GitHubPMAdapter)
    adapter._token = "ghp_test"
    adapter._owner = "owner"
    adapter._repo_name = "repo"
    adapter._project_number = 7
    adapter._project_node_id = "PVT_kgTest"
    adapter._gh = MagicMock()
    adapter._repo_obj = MagicMock()
    adapter._graphql = MagicMock()
    adapter._field_ids = _FIELD_IDS.copy()
    adapter._status_option_ids = {s.value: f"OPT_{s.value}" for s in TaskStatus}
    adapter._agent_role_option_ids = {r.value: f"OPT_{r.value}" for r in AgentRole}
    adapter._complexity_option_ids = {c.value: f"OPT_{c.value}" for c in Complexity}
    return adapter


def _items_page(issues: list[dict], has_next: bool = False) -> dict:
    return {
        "node": {
            "items": {
                "pageInfo": {"hasNextPage": has_next, "endCursor": None},
                "nodes": issues,
            }
        }
    }


def _issue_node(
    *,
    issue_id: str = "I_kgNode",
    number: int = 42,
    title: str = "Test task",
    body: str = "Do the thing",
    status: str = "pending",
    agent_role: str = "scaffold_agent",
    complexity: str = "medium",
    lineage_depth: int = 0,
    recovery_for: str | None = None,
    acceptance_criteria: str = "Works\nTests pass",
    depends_on: str = "",                       # comma-separated issue numbers
    milestone_number: int | None = 7,           # default matches get_tasks("7")
    state: str = "OPEN",
) -> dict:
    return {
        "content": {
            "id": issue_id,
            "number": number,
            "title": title,
            "body": body,
            "state": state,
            "milestone": {"number": milestone_number} if milestone_number is not None else None,
        },
        "fieldValues": {
            "nodes": [
                {"name": status,      "field": {"name": "Status"}},
                {"name": agent_role,  "field": {"name": "haive_agent_role"}},
                {"name": complexity,  "field": {"name": "haive_complexity"}},
                {"number": lineage_depth, "field": {"name": "haive_lineage_depth"}},
                {"text": recovery_for, "field": {"name": "haive_recovery_for"}},
                {"text": acceptance_criteria, "field": {"name": "haive_acceptance_criteria"}},
                {"text": depends_on,   "field": {"name": "haive_depends_on"}},
            ]
        },
    }


# ---------------------------------------------------------------------------
# TestGetProject
# ---------------------------------------------------------------------------

class TestGetProject:
    def test_returns_project_from_milestone(self):
        adapter = _make_adapter()
        ms = MagicMock()
        ms.title = "Add authentication"
        ms.description = "OAuth2 flow for the API"
        adapter._repo_obj.get_milestone.return_value = ms

        project = adapter.get_project("7")

        adapter._repo_obj.get_milestone.assert_called_once_with(7)
        assert project.project_id == "7"
        assert project.title == "Add authentication"
        assert project.description == "OAuth2 flow for the API"
        assert project.project_branch == "haive/project-7"

    def test_project_branch_derived_from_milestone_id(self):
        adapter = _make_adapter()
        ms = MagicMock()
        ms.title = "Sprint 3"
        ms.description = ""
        adapter._repo_obj.get_milestone.return_value = ms

        project = adapter.get_project("3")
        assert project.project_branch == "haive/project-3"

    def test_none_description_becomes_empty_string(self):
        adapter = _make_adapter()
        ms = MagicMock()
        ms.title = "No desc"
        ms.description = None
        adapter._repo_obj.get_milestone.return_value = ms

        project = adapter.get_project("1")
        assert project.description == ""

    def test_checkpoint_defaults_true_when_marker_absent(self):
        adapter = _make_adapter()
        ms = MagicMock()
        ms.title = "No marker"
        ms.description = "#Milestone\nSome milestone with no checkpoint marker."
        adapter._repo_obj.get_milestone.return_value = ms

        project = adapter.get_project("1")
        assert project.checkpoint is True

    def test_checkpoint_false_when_marker_present(self):
        adapter = _make_adapter()
        ms = MagicMock()
        ms.title = "Autonomous"
        ms.description = "#Milestone\nAuto milestone.\n#Checkpoint: false\n"
        adapter._repo_obj.get_milestone.return_value = ms

        project = adapter.get_project("1")
        assert project.checkpoint is False

    def test_checkpoint_true_when_marker_explicitly_true(self):
        adapter = _make_adapter()
        ms = MagicMock()
        ms.title = "Gated"
        ms.description = "#Checkpoint: true\n"
        adapter._repo_obj.get_milestone.return_value = ms

        project = adapter.get_project("1")
        assert project.checkpoint is True


# ---------------------------------------------------------------------------
# TestParseCheckpoint
# ---------------------------------------------------------------------------

class TestParseCheckpoint:
    def test_absent_defaults_true(self):
        assert _parse_checkpoint("No marker here at all.") is True

    def test_false_marker(self):
        assert _parse_checkpoint("#Checkpoint: false") is False

    def test_true_marker(self):
        assert _parse_checkpoint("#Checkpoint: true") is True

    def test_case_insensitive(self):
        assert _parse_checkpoint("#checkpoint: FALSE") is False

    def test_marker_amid_other_content(self):
        description = "#Milestone\nTitle\n\n#Checkpoint: false\n\n#Scope\nDo the thing.\n"
        assert _parse_checkpoint(description) is False

    def test_malformed_marker_defaults_true(self):
        assert _parse_checkpoint("#Checkpoint: maybe") is True

    def test_empty_string_defaults_true(self):
        assert _parse_checkpoint("") is True


# ---------------------------------------------------------------------------
# TestListOpenMilestones
# ---------------------------------------------------------------------------

class TestListOpenMilestones:
    def test_returns_milestone_summaries(self):
        adapter = _make_adapter()
        ms1 = MagicMock(number=10, title="First", due_on=datetime(2026, 6, 1, tzinfo=timezone.utc))
        ms2 = MagicMock(number=11, title="Second", due_on=None)
        adapter._repo_obj.get_milestones.return_value = [ms1, ms2]

        result = adapter.list_open_milestones()

        adapter._repo_obj.get_milestones.assert_called_once_with(state="open")
        assert [m.number for m in result] == [10, 11]
        assert result[0].title == "First"
        assert result[0].due_on == datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert result[1].due_on is None

    def test_empty_when_no_open_milestones(self):
        adapter = _make_adapter()
        adapter._repo_obj.get_milestones.return_value = []

        assert adapter.list_open_milestones() == []


# ---------------------------------------------------------------------------
# TestCloseMilestone
# ---------------------------------------------------------------------------

class TestCloseMilestone:
    def test_closes_the_milestone_by_number(self):
        adapter = _make_adapter()
        ms = MagicMock()
        adapter._repo_obj.get_milestone.return_value = ms

        adapter.close_milestone("7")

        adapter._repo_obj.get_milestone.assert_called_once_with(7)
        ms.edit.assert_called_once_with(state="closed")

    def test_github_exception_is_translated_to_runtime_error(self):
        # Regression test: github.GithubException must never cross the
        # adapters/ boundary — callers outside it (cli.py) only ever catch
        # RuntimeError, enforced by test_no_component_outside_adapters_imports_pygithub.
        adapter = _make_adapter()
        adapter._repo_obj.get_milestone.return_value.edit.side_effect = (
            github.GithubException(401, {"message": "Bad credentials"}, None)
        )

        with pytest.raises(RuntimeError, match="Bad credentials"):
            adapter.close_milestone("7")


# ---------------------------------------------------------------------------
# TestCloseCompletedTasks
# ---------------------------------------------------------------------------

class TestCloseCompletedTasks:
    def test_closes_only_complete_tasks(self):
        adapter = _make_adapter()
        adapter.get_tasks = MagicMock(return_value=[
            MagicMock(task_id="10", status=TaskStatus.COMPLETE),
            MagicMock(task_id="11", status=TaskStatus.BLOCKED),
            MagicMock(task_id="12", status=TaskStatus.COMPLETE),
        ])
        issues = {10: MagicMock(), 11: MagicMock(), 12: MagicMock()}
        adapter._repo_obj.get_issue.side_effect = lambda n: issues[n]

        adapter.close_completed_tasks("7")

        adapter.get_tasks.assert_called_once_with("7")
        issues[10].edit.assert_called_once_with(state="closed")
        issues[11].edit.assert_not_called()
        issues[12].edit.assert_called_once_with(state="closed")

    def test_no_complete_tasks_closes_nothing(self):
        adapter = _make_adapter()
        adapter.get_tasks = MagicMock(return_value=[
            MagicMock(task_id="10", status=TaskStatus.PENDING),
        ])

        adapter.close_completed_tasks("7")

        adapter._repo_obj.get_issue.assert_not_called()

    def test_github_exception_is_translated_to_runtime_error(self):
        # Regression test: github.GithubException must never cross the
        # adapters/ boundary — callers outside it (cli.py) only ever catch
        # RuntimeError, enforced by test_no_component_outside_adapters_imports_pygithub.
        adapter = _make_adapter()
        adapter.get_tasks = MagicMock(return_value=[
            MagicMock(task_id="10", status=TaskStatus.COMPLETE),
        ])
        adapter._repo_obj.get_issue.return_value.edit.side_effect = (
            github.GithubException(401, {"message": "Bad credentials"}, None)
        )

        with pytest.raises(RuntimeError, match="Bad credentials"):
            adapter.close_completed_tasks("7")


# ---------------------------------------------------------------------------
# TestGetTasks
# ---------------------------------------------------------------------------

class TestGetTasks:
    def test_maps_all_task_fields_correctly(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [_items_page([_issue_node()])]
        tasks = adapter.get_tasks("7")
        assert len(tasks) == 1
        t = tasks[0]
        assert t.task_id == "42"
        assert t.title == "Test task"
        assert t.description == "Do the thing"
        assert t.agent_role == AgentRole.SCAFFOLD_AGENT
        assert t.complexity == Complexity.MEDIUM
        assert t.status == TaskStatus.PENDING
        assert t.depends_on == []
        assert t.acceptance_criteria == ["Works", "Tests pass"]
        assert t.lineage_depth == 0
        assert t.recovery_for is None

    def test_maps_depends_on_from_field(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([_issue_node(number=10, depends_on="5, 7")]),
        ]
        tasks = adapter.get_tasks("7")
        assert tasks[0].depends_on == ["5", "7"]

    def test_maps_recovery_for_and_lineage_depth(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([_issue_node(recovery_for="8", lineage_depth=2)]),
        ]
        t = adapter.get_tasks("7")[0]
        assert t.recovery_for == "8"
        assert t.lineage_depth == 2

    def test_skips_non_issue_items(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([{"content": {}, "fieldValues": {"nodes": []}}]),
        ]
        tasks = adapter.get_tasks("7")
        assert tasks == []

    def test_paginates_multiple_pages(self):
        adapter = _make_adapter()
        page1 = {
            "node": {
                "items": {
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                    "nodes": [_issue_node(number=1, issue_id="I_1")],
                }
            }
        }
        page2 = _items_page([_issue_node(number=2, issue_id="I_2")])
        adapter._graphql.side_effect = [page1, page2]
        tasks = adapter.get_tasks("7")
        assert [t.task_id for t in tasks] == ["1", "2"]

    def test_filters_to_milestone(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([
                _issue_node(number=10, issue_id="I_10", milestone_number=7),
                _issue_node(number=20, issue_id="I_20", milestone_number=99),
            ]),
        ]
        tasks = adapter.get_tasks("7")
        assert len(tasks) == 1
        assert tasks[0].task_id == "10"

    def test_excludes_issues_with_no_milestone(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([_issue_node(number=5, milestone_number=None)]),
        ]
        tasks = adapter.get_tasks("7")
        assert tasks == []

    def test_excludes_closed_issues_even_if_still_on_board(self):
        # Closing an issue and removing it from the Projects v2 board are
        # separate GitHub operations — a closed issue can still be attached
        # to the board, and must never be treated as an active task.
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([
                _issue_node(number=10, issue_id="I_10", state="CLOSED"),
                _issue_node(number=20, issue_id="I_20", state="OPEN"),
            ]),
        ]
        tasks = adapter.get_tasks("7")
        assert len(tasks) == 1
        assert tasks[0].task_id == "20"

    def test_includes_closed_issue_if_haive_marked_it_complete(self):
        # Regression test: update_status() closes a task's issue when it
        # reaches COMPLETE, but that task must still be returned here — a
        # pending task depending on it resolves that dependency by looking
        # it up in get_tasks()'s result, and a completed dependency missing
        # from that list can never resolve, silently stranding anything
        # depending on it forever.
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([
                _issue_node(number=10, issue_id="I_10", state="CLOSED", status="complete"),
                _issue_node(number=20, issue_id="I_20", state="CLOSED", status="pending"),
            ]),
        ]
        tasks = adapter.get_tasks("7")
        assert len(tasks) == 1
        assert tasks[0].task_id == "10"
        assert tasks[0].status == TaskStatus.COMPLETE


# ---------------------------------------------------------------------------
# TestReadNewComments
# ---------------------------------------------------------------------------

class TestReadNewComments:
    _since = datetime(2026, 6, 1, tzinfo=timezone.utc)

    def _mock_comment(self, login: str, body: str, created_at: datetime) -> MagicMock:
        c = MagicMock()
        c.user.login = login
        c.body = body
        c.created_at = created_at
        return c

    def test_returns_comments_for_issues_in_project(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [_items_page([_issue_node(number=10)])]
        now = datetime(2026, 6, 22, tzinfo=timezone.utc)
        comment = self._mock_comment("alice", "LGTM", now)
        adapter._repo_obj.get_issue.return_value.get_comments.return_value = [comment]
        comments = adapter.read_new_comments("7", self._since)
        assert len(comments) == 1
        assert comments[0].task_id == "10"
        assert comments[0].author == "alice"
        assert comments[0].body == "LGTM"
        assert comments[0].created_at == now

    def test_collects_comments_across_multiple_issues(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([_issue_node(number=1, issue_id="I_1"), _issue_node(number=2, issue_id="I_2")])
        ]
        now = datetime(2026, 6, 22, tzinfo=timezone.utc)
        def get_issue_side_effect(n):
            m = MagicMock()
            m.get_comments.return_value = [self._mock_comment("bob", f"comment on {n}", now)]
            return m
        adapter._repo_obj.get_issue.side_effect = get_issue_side_effect
        comments = adapter.read_new_comments("7", self._since)
        assert len(comments) == 2
        task_ids = {c.task_id for c in comments}
        assert task_ids == {"1", "2"}

    def test_passes_since_to_pygithub(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [_items_page([_issue_node(number=5)])]
        adapter._repo_obj.get_issue.return_value.get_comments.return_value = []
        adapter.read_new_comments("7", self._since)
        adapter._repo_obj.get_issue.return_value.get_comments.assert_called_once_with(since=self._since)

    def test_excludes_comments_from_other_milestones(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([
                _issue_node(number=10, issue_id="I_10", milestone_number=7),
                _issue_node(number=20, issue_id="I_20", milestone_number=99),
            ])
        ]
        now = datetime(2026, 6, 22, tzinfo=timezone.utc)
        def get_issue_side_effect(n):
            m = MagicMock()
            m.get_comments.return_value = [self._mock_comment("alice", f"comment on {n}", now)]
            return m
        adapter._repo_obj.get_issue.side_effect = get_issue_side_effect

        comments = adapter.read_new_comments("7", self._since)

        assert len(comments) == 1
        assert comments[0].task_id == "10"

    def test_excludes_comments_from_closed_issues(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([
                _issue_node(number=10, issue_id="I_10", state="OPEN"),
                _issue_node(number=20, issue_id="I_20", state="CLOSED"),
            ])
        ]
        adapter._repo_obj.get_issue.return_value.get_comments.return_value = []

        adapter.read_new_comments("7", self._since)

        adapter._repo_obj.get_issue.assert_called_once_with(10)


# ---------------------------------------------------------------------------
# TestStartupValidation
# ---------------------------------------------------------------------------

class TestStartupValidation:
    def _make_gql_fn(self, responses: list[dict]):
        idx = 0
        def gql(query: str, variables: dict) -> dict:
            nonlocal idx
            result = responses[idx]
            idx += 1
            return result
        return gql

    def test_missing_field_raises_runtime_error(self):
        missing_response = {
            "node": {
                "fields": {
                    "nodes": [
                        {"name": "haive_agent_role"},
                        # haive_complexity intentionally absent
                        {"name": "haive_depends_on"},
                        {"name": "haive_lineage_depth"},
                        {"name": "haive_recovery_for"},
                        {"name": "haive_acceptance_criteria"},
                    ]
                }
            }
        }
        gql = self._make_gql_fn([_RESOLVE_RESPONSE, missing_response])
        with patch("haive.adapters.pm.github.github.Github"):
            with patch.object(GitHubPMAdapter, "_graphql", lambda self, q, v: gql(q, v)):
                with pytest.raises(RuntimeError, match="haive_complexity"):
                    GitHubPMAdapter(_fake_settings())

    def test_error_lists_all_missing_fields(self):
        empty_fields = {"node": {"fields": {"nodes": []}}}
        gql = self._make_gql_fn([_RESOLVE_RESPONSE, empty_fields])
        with patch("haive.adapters.pm.github.github.Github"):
            with patch.object(GitHubPMAdapter, "_graphql", lambda self, q, v: gql(q, v)):
                with pytest.raises(RuntimeError) as exc_info:
                    GitHubPMAdapter(_fake_settings())
        msg = str(exc_info.value)
        for field in ("haive_agent_role", "haive_complexity", "haive_depends_on",
                      "haive_lineage_depth", "haive_recovery_for", "haive_acceptance_criteria"):
            assert field in msg

    def test_all_fields_present_initializes_cleanly(self):
        gql = self._make_gql_fn(_CONSTRUCTOR_RESPONSES)
        with patch("haive.adapters.pm.github.github.Github"):
            with patch.object(GitHubPMAdapter, "_graphql", lambda self, q, v: gql(q, v)):
                adapter = GitHubPMAdapter(_fake_settings())
        assert adapter._project_node_id == "PVT_kgTest"

    def test_project_not_found_raises_runtime_error(self):
        not_found = {"repository": {"owner": {}}}
        gql = self._make_gql_fn([not_found])
        with patch("haive.adapters.pm.github.github.Github"):
            with patch.object(GitHubPMAdapter, "_graphql", lambda self, q, v: gql(q, v)):
                with pytest.raises(RuntimeError, match="not found"):
                    GitHubPMAdapter(_fake_settings())

    def test_missing_github_token_raises_value_error(self):
        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            GitHubPMAdapter(_fake_settings(github_token=None))

    def test_missing_github_repo_raises_value_error(self):
        with pytest.raises(ValueError, match="GITHUB_REPO"):
            GitHubPMAdapter(_fake_settings(github_repo=None))

    def test_missing_project_id_raises_value_error(self):
        with pytest.raises(ValueError, match="GITHUB_PROJECT_ID"):
            GitHubPMAdapter(_fake_settings(github_project_id=None))

    def test_malformed_github_repo_raises_value_error(self):
        with pytest.raises(ValueError, match="owner/repo"):
            GitHubPMAdapter(_fake_settings(github_repo="just-a-repo-name"))


# ---------------------------------------------------------------------------
# TestAdapterBoundaries
# ---------------------------------------------------------------------------

class TestAdapterBoundaries:
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


# ---------------------------------------------------------------------------
# TestCreateTask
# ---------------------------------------------------------------------------

class TestCreateTask:
    def _make_task(self, **overrides: object) -> MagicMock:
        t = MagicMock()
        t.title = overrides.get("title", "Build the thing")
        t.description = overrides.get("description", "Do the work")
        t.agent_role = overrides.get("agent_role", AgentRole.SCAFFOLD_AGENT)
        t.complexity = overrides.get("complexity", Complexity.LOW)
        t.lineage_depth = overrides.get("lineage_depth", 0)
        t.recovery_for = overrides.get("recovery_for", None)
        t.acceptance_criteria = overrides.get("acceptance_criteria", ["Works"])
        return t

    def _add_response(self) -> dict:
        return {"addProjectV2ItemById": {"item": {"id": "PVTI_item1"}}}

    def _update_response(self) -> dict:
        return {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_item1"}}}

    def test_creates_issue_and_returns_task_id(self):
        adapter = _make_adapter()
        ms = MagicMock()
        adapter._repo_obj.get_milestone.return_value = ms
        gh_issue = MagicMock()
        gh_issue.number = 42
        gh_issue.raw_data = {"node_id": "I_node42"}
        adapter._repo_obj.create_issue.return_value = gh_issue
        adapter._graphql.side_effect = [self._add_response()] + [self._update_response()] * 6

        task_id = adapter.create_task("1", self._make_task())

        assert task_id == "42"
        adapter._repo_obj.create_issue.assert_called_once_with(
            title="Build the thing",
            body="Do the work",
            milestone=ms,
        )

    def test_makes_seven_graphql_calls(self):
        adapter = _make_adapter()
        adapter._repo_obj.get_milestone.return_value = MagicMock()
        gh_issue = MagicMock()
        gh_issue.number = 1
        gh_issue.raw_data = {"node_id": "I_node1"}
        adapter._repo_obj.create_issue.return_value = gh_issue
        adapter._graphql.side_effect = [self._add_response()] + [self._update_response()] * 6

        adapter.create_task("1", self._make_task())

        assert adapter._graphql.call_count == 7  # 1 add + 6 field updates

    def test_acceptance_criteria_joined_with_newline(self):
        adapter = _make_adapter()
        adapter._repo_obj.get_milestone.return_value = MagicMock()
        gh_issue = MagicMock()
        gh_issue.number = 1
        gh_issue.raw_data = {"node_id": "I_node1"}
        adapter._repo_obj.create_issue.return_value = gh_issue

        calls: list[dict] = []
        def capture(q: str, v: dict) -> dict:
            calls.append(v)
            if "addProjectV2ItemById" in q:
                return self._add_response()
            return self._update_response()
        adapter._graphql.side_effect = capture

        adapter.create_task("1", self._make_task(acceptance_criteria=["Step A", "Step B"]))

        criteria_call = calls[-1]
        assert criteria_call["value"] == {"text": "Step A\nStep B"}

    def test_lineage_depth_passed_as_float(self):
        adapter = _make_adapter()
        adapter._repo_obj.get_milestone.return_value = MagicMock()
        gh_issue = MagicMock()
        gh_issue.number = 1
        gh_issue.raw_data = {"node_id": "I_node1"}
        adapter._repo_obj.create_issue.return_value = gh_issue

        calls: list[dict] = []
        def capture(q: str, v: dict) -> dict:
            calls.append(v)
            if "addProjectV2ItemById" in q:
                return self._add_response()
            return self._update_response()
        adapter._graphql.side_effect = capture

        adapter.create_task("1", self._make_task(lineage_depth=3))

        lineage_call = next(c for c in calls if c.get("value") == {"number": 3.0})
        assert lineage_call["fieldId"] == "F_lineage_depth"


# ---------------------------------------------------------------------------
# TestSetDependency
# ---------------------------------------------------------------------------

class TestSetDependency:
    def test_updates_haive_depends_on_with_comma_joined_ids(self):
        adapter = _make_adapter()
        adapter._get_project_item_id = MagicMock(return_value="PVTI_item1")
        adapter._graphql.return_value = {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_item1"}}}

        adapter.set_dependency("42", ["1", "3"])

        call_vars = adapter._graphql.call_args[0][1]
        assert call_vars["value"] == {"text": "1, 3"}
        assert call_vars["fieldId"] == "F_depends_on"

    def test_empty_depends_on_sets_empty_string(self):
        adapter = _make_adapter()
        adapter._get_project_item_id = MagicMock(return_value="PVTI_item1")
        adapter._graphql.return_value = {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_item1"}}}

        adapter.set_dependency("42", [])

        call_vars = adapter._graphql.call_args[0][1]
        assert call_vars["value"] == {"text": ""}


# ---------------------------------------------------------------------------
# TestUpdateStatus
# ---------------------------------------------------------------------------

class TestUpdateStatus:
    def test_sets_correct_option_id_for_status(self):
        adapter = _make_adapter()
        adapter._get_project_item_id = MagicMock(return_value="PVTI_item1")
        adapter._graphql.return_value = {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_item1"}}}

        adapter.update_status("42", TaskStatus.IN_PROGRESS)

        call_vars = adapter._graphql.call_args[0][1]
        assert call_vars["fieldId"] == "F_status"
        assert call_vars["value"] == {"singleSelectOptionId": "OPT_in_progress"}

    def test_each_status_value_maps_to_its_option_id(self):
        adapter = _make_adapter()
        adapter._get_project_item_id = MagicMock(return_value="PVTI_item1")
        adapter._graphql.return_value = {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_item1"}}}

        for status in TaskStatus:
            adapter._graphql.reset_mock()
            adapter.update_status("1", status)
            call_vars = adapter._graphql.call_args[0][1]
            assert call_vars["value"] == {"singleSelectOptionId": f"OPT_{status.value}"}


# ---------------------------------------------------------------------------
# TestAddComment
# ---------------------------------------------------------------------------

class TestAddComment:
    def test_creates_comment_on_issue(self):
        adapter = _make_adapter()

        adapter.add_comment("42", "Great work!")

        adapter._repo_obj.get_issue.assert_called_once_with(42)
        adapter._repo_obj.get_issue.return_value.create_comment.assert_called_once_with("Great work!")

    def test_task_id_parsed_as_int(self):
        adapter = _make_adapter()
        adapter.add_comment("7", "Done")
        adapter._repo_obj.get_issue.assert_called_once_with(7)
