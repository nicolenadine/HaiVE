from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from haive.adapters.pm import board_setup
from haive.models.enums import AgentRole, Complexity, TaskStatus


def _response(data: dict, errors: list | None = None) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"data": data} if errors is None else {"data": data, "errors": errors}
    return resp


_REPO_QUERY_RESULT = {
    "repositoryOwner": {"id": "O_owner", "projectsV2": {"nodes": []}},
    "repository": {"id": "R_repo"},
}

_CREATE_PROJECT_RESULT = {
    "createProjectV2": {
        "projectV2": {"id": "PVT_new", "title": "repo Haive", "number": 7, "url": "https://x/7"}
    }
}

_EMPTY_FIELDS_RESULT = {"node": {"fields": {"nodes": []}}}


def _all_fields_present_result(status_options: list[str] | None = None) -> dict:
    nodes = [
        {"id": f"F_{name}", "name": name, "dataType": dtype}
        for name, dtype, _ in board_setup._CUSTOM_FIELDS
    ]
    for n, (name, dtype, options) in zip(nodes, board_setup._CUSTOM_FIELDS):
        if options:
            n["options"] = [{"name": o["name"]} for o in options]
    status_names = status_options if status_options is not None else [o["name"] for o in board_setup._STATUS_OPTIONS]
    nodes.append({"id": "F_status", "name": "Status", "dataType": "SINGLE_SELECT",
                  "options": [{"name": n} for n in status_names]})
    return {"node": {"fields": {"nodes": nodes}}}


class TestFindOrCreateProject:
    def test_creates_new_project_when_none_exists(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.side_effect = [
                _response(_REPO_QUERY_RESULT),
                _response(_CREATE_PROJECT_RESULT),
            ]
            project, repo_id, created = board_setup._find_or_create_project(
                "tok", "owner", "repo", "repo Haive"
            )
        assert created is True
        assert project["number"] == 7
        assert repo_id == "R_repo"

    def test_reuses_existing_open_project_with_matching_title(self):
        repo_result = {
            "repositoryOwner": {
                "id": "O_owner",
                "projectsV2": {"nodes": [
                    {"id": "PVT_existing", "title": "repo Haive", "number": 3, "url": "https://x/3", "closed": False},
                ]},
            },
            "repository": {"id": "R_repo"},
        }
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.return_value = _response(repo_result)
            project, repo_id, created = board_setup._find_or_create_project(
                "tok", "owner", "repo", "repo Haive"
            )
        assert created is False
        assert project["number"] == 3
        mock_post.assert_called_once()  # only the lookup query — no create mutation

    def test_ignores_closed_project_with_same_title(self):
        repo_result = {
            "repositoryOwner": {
                "id": "O_owner",
                "projectsV2": {"nodes": [
                    {"id": "PVT_old", "title": "repo Haive", "number": 1, "url": "https://x/1", "closed": True},
                ]},
            },
            "repository": {"id": "R_repo"},
        }
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.side_effect = [_response(repo_result), _response(_CREATE_PROJECT_RESULT)]
            project, repo_id, created = board_setup._find_or_create_project(
                "tok", "owner", "repo", "repo Haive"
            )
        assert created is True

    def test_missing_repository_raises(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.return_value = _response({"repositoryOwner": None, "repository": None})
            with pytest.raises(RuntimeError, match="not found"):
                board_setup._find_or_create_project("tok", "owner", "ghost", "title")


class TestCreateCustomFields:
    def test_creates_all_missing_fields(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.side_effect = [_response(_EMPTY_FIELDS_RESULT)] + [
                _response({"createProjectV2Field": {"projectV2Field": {"name": name}}})
                for name, _, _ in board_setup._CUSTOM_FIELDS
            ]
            created, existing = board_setup._create_custom_fields("tok", "PVT_1")
        assert set(created) == {name for name, _, _ in board_setup._CUSTOM_FIELDS}
        assert existing == []

    def test_skips_fields_that_already_exist(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.return_value = _response(_all_fields_present_result())
            created, existing = board_setup._create_custom_fields("tok", "PVT_1")
        assert created == []
        assert set(existing) == {name for name, _, _ in board_setup._CUSTOM_FIELDS}
        mock_post.assert_called_once()  # only the fetch — no create mutations


class TestConfigureStatus:
    def test_updates_when_options_differ(self):
        wrong_status_result = _all_fields_present_result(status_options=["todo", "done"])
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.side_effect = [
                _response(wrong_status_result),
                _response({"updateProjectV2Field": {"projectV2Field": {"name": "Status"}}}),
            ]
            updated = board_setup._configure_status("tok", "PVT_1")
        assert updated is True

    def test_skips_when_already_correct(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.return_value = _response(_all_fields_present_result())
            updated = board_setup._configure_status("tok", "PVT_1")
        assert updated is False
        mock_post.assert_called_once()

    def test_returns_false_when_status_field_missing(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.return_value = _response(_EMPTY_FIELDS_RESULT)
            updated = board_setup._configure_status("tok", "PVT_1")
        assert updated is False


class TestVerify:
    def test_no_issues_when_everything_matches(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.return_value = _response(_all_fields_present_result())
            issues = board_setup._verify("tok", "PVT_1")
        assert issues == []

    def test_reports_missing_fields(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.return_value = _response(_EMPTY_FIELDS_RESULT)
            issues = board_setup._verify("tok", "PVT_1")
        assert any("haive_agent_role" in issue for issue in issues)
        assert any("Status" in issue for issue in issues)

    def test_reports_option_mismatch(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.return_value = _response(_all_fields_present_result(status_options=["todo", "done"]))
            issues = board_setup._verify("tok", "PVT_1")
        assert any("Status" in issue for issue in issues)


class TestGraphqlErrorHandling:
    def test_raises_runtime_error_on_graphql_errors(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.return_value = _response({}, errors=[{"message": "bad query"}])
            with pytest.raises(RuntimeError, match="bad query"):
                board_setup._graphql("tok", "query {}", {})


class TestSetupBoardIntegration:
    def test_full_flow_new_project(self):
        with patch("haive.adapters.pm.board_setup.requests.post") as mock_post:
            mock_post.side_effect = [
                _response(_REPO_QUERY_RESULT),           # find_or_create: lookup
                _response(_CREATE_PROJECT_RESULT),        # find_or_create: create
                _response({"linkProjectV2ToRepository": {"repository": {"nameWithOwner": "owner/repo"}}}),
                _response(_EMPTY_FIELDS_RESULT),           # create_custom_fields: fetch
                *[
                    _response({"createProjectV2Field": {"projectV2Field": {"name": name}}})
                    for name, _, _ in board_setup._CUSTOM_FIELDS
                ],
                _response(_EMPTY_FIELDS_RESULT),           # configure_status: fetch (no Status field yet)
                _response(_all_fields_present_result()),   # verify: fetch
            ]
            result = board_setup.setup_board("tok", "owner", "repo", "repo Haive")

        assert result.project_number == 7
        assert result.created_project is True
        assert set(result.fields_created) == {name for name, _, _ in board_setup._CUSTOM_FIELDS}
        assert result.status_updated is False  # Status field didn't exist to update
        assert result.verified is True
        assert result.verification_issues == []


class TestOptionListsMatchEnums:
    def test_agent_role_options_cover_every_enum_value(self):
        role_field = next(f for f in board_setup._CUSTOM_FIELDS if f[0] == "haive_agent_role")
        names = {o["name"] for o in role_field[2]}
        assert names == {r.value for r in AgentRole}

    def test_complexity_options_cover_every_enum_value(self):
        complexity_field = next(f for f in board_setup._CUSTOM_FIELDS if f[0] == "haive_complexity")
        names = {o["name"] for o in complexity_field[2]}
        assert names == {c.value for c in Complexity}

    def test_status_options_cover_every_enum_value(self):
        names = {o["name"] for o in board_setup._STATUS_OPTIONS}
        assert names == {s.value for s in TaskStatus}
