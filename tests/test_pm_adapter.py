from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from haive.adapters.pm.github import GitHubPMAdapter
from haive.models.enums import AgentRole, Complexity, TaskStatus

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
    milestone: dict | None = None,
) -> dict:
    return {
        "content": {
            "id": issue_id,
            "number": number,
            "title": title,
            "body": body,
            "milestone": milestone,
        },
        "fieldValues": {
            "nodes": [
                {"name": status,      "field": {"name": "Status"}},
                {"name": agent_role,  "field": {"name": "haive_agent_role"}},
                {"name": complexity,  "field": {"name": "haive_complexity"}},
                {"number": lineage_depth, "field": {"name": "haive_lineage_depth"}},
                {"text": recovery_for, "field": {"name": "haive_recovery_for"}},
                {"text": acceptance_criteria, "field": {"name": "haive_acceptance_criteria"}},
            ]
        },
    }


def _no_relationships() -> dict:
    return {"node": {"issueRelationships": {"nodes": []}}}


def _relationships(*blocking_numbers: int) -> dict:
    return {
        "node": {
            "issueRelationships": {
                "nodes": [
                    {"type": "IS_BLOCKED_BY", "relatedIssue": {"number": n}}
                    for n in blocking_numbers
                ]
            }
        }
    }


# ---------------------------------------------------------------------------
# TestGetTasks
# ---------------------------------------------------------------------------

class TestGetTasks:
    def test_maps_all_task_fields_correctly(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([_issue_node()]),
            _no_relationships(),
        ]
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

    def test_maps_depends_on_from_blocked_by(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([_issue_node(number=10)]),
            _relationships(5, 7),
        ]
        tasks = adapter.get_tasks("7")
        assert tasks[0].depends_on == ["5", "7"]

    def test_maps_recovery_for_and_lineage_depth(self):
        adapter = _make_adapter()
        adapter._graphql.side_effect = [
            _items_page([_issue_node(recovery_for="8", lineage_depth=2)]),
            _no_relationships(),
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
        # _fetch_project_items exhausts all pages before _get_blocked_by is called
        adapter._graphql.side_effect = [
            page1,
            page2,
            _no_relationships(),  # blocked_by for issue 1
            _no_relationships(),  # blocked_by for issue 2
        ]
        tasks = adapter.get_tasks("7")
        assert [t.task_id for t in tasks] == ["1", "2"]


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
        adapter._graphql.return_value = _items_page([_issue_node(number=10)])["node"]["items"]
        # Override: _fetch_project_items is what actually uses _graphql
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
        for field in ("haive_agent_role", "haive_complexity", "haive_lineage_depth",
                      "haive_recovery_for", "haive_acceptance_criteria"):
            assert field in msg

    def test_all_fields_present_initializes_cleanly(self):
        gql = self._make_gql_fn(_CONSTRUCTOR_RESPONSES)
        with patch("haive.adapters.pm.github.github.Github"):
            with patch.object(GitHubPMAdapter, "_graphql", lambda self, q, v: gql(q, v)):
                adapter = GitHubPMAdapter(_fake_settings())
        assert adapter._project_node_id == "PVT_kgTest"

    def test_project_not_found_raises_runtime_error(self):
        not_found = {"repository": {"owner": {}}}  # no projectV2 key
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
# TestGetBlockedBy
# ---------------------------------------------------------------------------

class TestGetBlockedBy:
    def test_returns_issue_numbers_for_is_blocked_by(self):
        adapter = _make_adapter()
        adapter._graphql.return_value = _relationships(3, 7)
        result = adapter._get_blocked_by("I_kgNode")
        assert result == [3, 7]

    def test_ignores_other_relationship_types(self):
        adapter = _make_adapter()
        adapter._graphql.return_value = {
            "node": {
                "issueRelationships": {
                    "nodes": [
                        {"type": "BLOCKS", "relatedIssue": {"number": 99}},
                        {"type": "IS_BLOCKED_BY", "relatedIssue": {"number": 5}},
                        {"type": "DUPLICATE_OF", "relatedIssue": {"number": 88}},
                    ]
                }
            }
        }
        result = adapter._get_blocked_by("I_kgNode")
        assert result == [5]

    def test_returns_empty_list_when_no_relationships(self):
        adapter = _make_adapter()
        adapter._graphql.return_value = _no_relationships()
        result = adapter._get_blocked_by("I_kgNode")
        assert result == []

    def test_no_component_outside_adapters_imports_pygithub(self):
        import importlib, sys
        for mod_name, mod in list(sys.modules.items()):
            if mod_name.startswith("haive.") and not mod_name.startswith("haive.adapters"):
                source = getattr(mod, "__file__", "") or ""
                if source.endswith(".py"):
                    with open(source) as f:
                        content = f.read()
                    assert "import github" not in content and "from github" not in content, \
                        f"{mod_name} must not import PyGithub"
