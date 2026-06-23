from __future__ import annotations

from datetime import datetime
from typing import Any

import github
import requests
from pydantic import BaseModel

from haive.models.config import Settings
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.task import Project, Task, TaskComment

_REQUIRED_CUSTOM_FIELDS = frozenset({
    "haive_agent_role",
    "haive_complexity",
    "haive_depends_on",
    "haive_lineage_depth",
    "haive_recovery_for",
    "haive_acceptance_criteria",
})

_GH_STATUS_MAP: dict[str, TaskStatus] = {
    "pending":            TaskStatus.PENDING,
    "in_progress":        TaskStatus.IN_PROGRESS,
    "in progress":        TaskStatus.IN_PROGRESS,
    "complete":           TaskStatus.COMPLETE,
    "needs_human_review": TaskStatus.NEEDS_HUMAN_REVIEW,
    "blocked":            TaskStatus.BLOCKED,
    "skipped":            TaskStatus.SKIPPED,
}

_GRAPHQL_URL = "https://api.github.com/graphql"


class _GitHubIssue(BaseModel):
    issue_node_id:             str
    issue_number:              int
    title:                     str
    body:                      str
    gh_status:                 str
    haive_depends_on:          str = ""
    milestone_id:              int | None
    haive_agent_role:          str
    haive_complexity:          str
    haive_lineage_depth:       int
    haive_recovery_for:        str | None
    haive_acceptance_criteria: str


class _GitHubMilestone(BaseModel):
    milestone_id:   int
    title:          str
    description:    str
    state:          str
    project_branch: str


class GitHubPMAdapter:
    def __init__(self, settings: Settings) -> None:
        if not settings.github_token:
            raise ValueError("GitHubPMAdapter requires GITHUB_TOKEN in settings.")
        if not settings.github_repo:
            raise ValueError("GitHubPMAdapter requires GITHUB_REPO in settings.")
        if not settings.github_project_id:
            raise ValueError("GitHubPMAdapter requires GITHUB_PROJECT_ID in settings.")
        if "/" not in settings.github_repo:
            raise ValueError(
                f"GITHUB_REPO must be in 'owner/repo' format, got: {settings.github_repo!r}"
            )
        self._token = settings.github_token
        self._owner, self._repo_name = settings.github_repo.split("/", 1)
        self._project_number = settings.github_project_id
        self._gh = github.Github(settings.github_token)
        self._repo_obj = self._gh.get_repo(settings.github_repo)
        self._project_node_id: str | None = None
        self._field_ids: dict[str, str] = {}
        self._status_option_ids: dict[str, str] = {}
        self._agent_role_option_ids: dict[str, str] = {}
        self._complexity_option_ids: dict[str, str] = {}
        self._validate_custom_fields()

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        resp = requests.post(
            _GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"GitHub GraphQL error: {data['errors']}")
        return data["data"]

    def _resolve_project_node_id(self) -> str:
        if self._project_node_id is not None:
            return self._project_node_id
        query = """
        query($owner: String!, $repo: String!, $number: Int!) {
          repository(owner: $owner, name: $repo) {
            owner {
              ... on User         { projectV2(number: $number) { id } }
              ... on Organization { projectV2(number: $number) { id } }
            }
          }
        }
        """
        data = self._graphql(query, {
            "owner": self._owner,
            "repo": self._repo_name,
            "number": self._project_number,
        })
        project = data["repository"]["owner"].get("projectV2")
        if not project:
            raise RuntimeError(
                f"GitHub Project #{self._project_number} not found for owner '{self._owner}'."
            )
        node_id: str = project["id"]
        self._project_node_id = node_id
        return node_id

    def _validate_custom_fields(self) -> None:
        node_id = self._resolve_project_node_id()
        query = """
        query($projectId: ID!) {
          node(id: $projectId) {
            ... on ProjectV2 {
              fields(first: 50) {
                nodes {
                  ... on ProjectV2FieldCommon { id name }
                  ... on ProjectV2SingleSelectField { id name options { id name } }
                }
              }
            }
          }
        }
        """
        data = self._graphql(query, {"projectId": node_id})
        field_names: set[str] = set()
        for node in data["node"]["fields"]["nodes"]:
            name = node.get("name", "")
            fid = node.get("id", "")
            if not name:
                continue
            field_names.add(name)
            if fid:
                self._field_ids[name] = fid
            if "options" in node:
                option_map = {opt["name"]: opt["id"] for opt in node["options"]}
                if name == "Status":
                    self._status_option_ids = option_map
                elif name == "haive_agent_role":
                    self._agent_role_option_ids = option_map
                elif name == "haive_complexity":
                    self._complexity_option_ids = option_map
        missing = _REQUIRED_CUSTOM_FIELDS - field_names
        if missing:
            raise RuntimeError(
                f"GitHub Project is missing required haive custom fields: {sorted(missing)}. "
                "Add these fields to the project before running haive."
            )

    def _extract_field_values(self, field_value_nodes: list[dict[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for node in field_value_nodes:
            field_name = node.get("field", {}).get("name", "")
            if not field_name.startswith("haive_") and field_name != "Status":
                continue
            if "name" in node:
                result[field_name] = node["name"]
            elif "text" in node:
                result[field_name] = node["text"]
            elif "number" in node:
                result[field_name] = node["number"]
        return result

    def _map_issue_to_task(self, issue: _GitHubIssue) -> Task:
        status = _GH_STATUS_MAP.get(issue.gh_status.lower(), TaskStatus.PENDING)
        criteria = [line.strip() for line in issue.haive_acceptance_criteria.splitlines() if line.strip()]
        return Task(
            task_id=str(issue.issue_number),
            title=issue.title,
            description=issue.body,
            agent_role=AgentRole(issue.haive_agent_role),
            complexity=Complexity(issue.haive_complexity),
            depends_on=[s.strip() for s in issue.haive_depends_on.split(",") if s.strip()],
            acceptance_criteria=criteria,
            status=status,
            recovery_for=issue.haive_recovery_for or None,
            lineage_depth=issue.haive_lineage_depth,
        )

    def _fetch_project_items(self) -> list[dict[str, Any]]:
        node_id = self._resolve_project_node_id()
        query = """
        query($projectId: ID!, $after: String) {
          node(id: $projectId) {
            ... on ProjectV2 {
              items(first: 100, after: $after) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  content {
                    ... on Issue {
                      id
                      number
                      title
                      body
                      milestone { number }
                    }
                  }
                  fieldValues(first: 20) {
                    nodes {
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name
                        field { ... on ProjectV2FieldCommon { name } }
                      }
                      ... on ProjectV2ItemFieldTextValue {
                        text
                        field { ... on ProjectV2FieldCommon { name } }
                      }
                      ... on ProjectV2ItemFieldNumberValue {
                        number
                        field { ... on ProjectV2FieldCommon { name } }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            data = self._graphql(query, {"projectId": node_id, "after": cursor})
            page = data["node"]["items"]
            items.extend(page["nodes"])
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
        return items

    def get_project(self, project_id: str) -> Project:
        ms = self._repo_obj.get_milestone(int(project_id))
        return Project(
            project_id=project_id,
            title=ms.title,
            description=ms.description or "",
            project_branch=f"haive/project-{project_id}",
        )

    def get_tasks(self, project_id: str) -> list[Task]:
        milestone_number = int(project_id)
        raw_items = self._fetch_project_items()
        tasks: list[Task] = []
        for item in raw_items:
            content = item.get("content")
            if not content or "number" not in content:
                continue
            # Only include issues assigned to this milestone
            item_milestone = content.get("milestone")
            if not item_milestone or item_milestone.get("number") != milestone_number:
                continue
            fields = self._extract_field_values(item.get("fieldValues", {}).get("nodes", []))
            milestone = content.get("milestone")
            gh_issue = _GitHubIssue(
                issue_node_id=content["id"],
                issue_number=content["number"],
                title=content.get("title", ""),
                body=content.get("body", ""),
                gh_status=fields.get("Status", "pending"),
                haive_depends_on=fields.get("haive_depends_on") or "",
                milestone_id=milestone["number"] if milestone else None,
                haive_agent_role=fields.get("haive_agent_role", ""),
                haive_complexity=fields.get("haive_complexity", "low"),
                haive_lineage_depth=int(fields.get("haive_lineage_depth") or 0),
                haive_recovery_for=fields.get("haive_recovery_for") or None,
                haive_acceptance_criteria=fields.get("haive_acceptance_criteria") or "",
            )
            tasks.append(self._map_issue_to_task(gh_issue))
        return tasks

    def read_new_comments(self, project_id: str, since: datetime) -> list[TaskComment]:
        raw_items = self._fetch_project_items()
        comments: list[TaskComment] = []
        for item in raw_items:
            content = item.get("content")
            if not content or "number" not in content:
                continue
            issue_number = content["number"]
            gh_issue = self._repo_obj.get_issue(issue_number)
            for comment in gh_issue.get_comments(since=since):
                comments.append(TaskComment(
                    task_id=str(issue_number),
                    author=comment.user.login,
                    body=comment.body,
                    created_at=comment.created_at,
                ))
        return comments

    def _get_project_item_id(self, task_id: str) -> str:
        gh_issue = self._repo_obj.get_issue(int(task_id))
        issue_node_id: str = gh_issue.raw_data["node_id"]
        query = """
        query($issueId: ID!) {
          node(id: $issueId) {
            ... on Issue {
              projectItems(first: 10) {
                nodes { id project { id } }
              }
            }
          }
        }
        """
        data = self._graphql(query, {"issueId": issue_node_id})
        project_node_id = self._resolve_project_node_id()
        for item in data["node"]["projectItems"]["nodes"]:
            if item["project"]["id"] == project_node_id:
                return item["id"]
        raise RuntimeError(
            f"Issue #{task_id} is not on the haive project board."
        )

    def _update_field(self, item_id: str, field_name: str, value: dict[str, Any]) -> None:
        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
          updateProjectV2ItemFieldValue(input: {
            projectId: $projectId
            itemId: $itemId
            fieldId: $fieldId
            value: $value
          }) { projectV2Item { id } }
        }
        """
        self._graphql(mutation, {
            "projectId": self._resolve_project_node_id(),
            "itemId": item_id,
            "fieldId": self._field_ids[field_name],
            "value": value,
        })

    def create_task(self, project_id: str, task: Any) -> str:
        milestone_obj = self._repo_obj.get_milestone(int(project_id))
        gh_issue = self._repo_obj.create_issue(
            title=task.title,
            body=task.description,
            milestone=milestone_obj,
        )
        content_node_id: str = gh_issue.raw_data["node_id"]
        add_mutation = """
        mutation($projectId: ID!, $contentId: ID!) {
          addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
            item { id }
          }
        }
        """
        result = self._graphql(add_mutation, {
            "projectId": self._resolve_project_node_id(),
            "contentId": content_node_id,
        })
        item_id: str = result["addProjectV2ItemById"]["item"]["id"]
        self._update_field(item_id, "haive_agent_role", {
            "singleSelectOptionId": self._agent_role_option_ids[task.agent_role.value],
        })
        self._update_field(item_id, "haive_complexity", {
            "singleSelectOptionId": self._complexity_option_ids[task.complexity.value],
        })
        self._update_field(item_id, "haive_depends_on", {"text": ""})
        self._update_field(item_id, "haive_lineage_depth", {"number": float(task.lineage_depth)})
        self._update_field(item_id, "haive_recovery_for", {"text": task.recovery_for or ""})
        self._update_field(item_id, "haive_acceptance_criteria", {
            "text": "\n".join(task.acceptance_criteria),
        })
        return str(gh_issue.number)

    def set_dependency(self, task_id: str, depends_on: list[str]) -> None:
        item_id = self._get_project_item_id(task_id)
        self._update_field(item_id, "haive_depends_on", {"text": ", ".join(depends_on)})

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        item_id = self._get_project_item_id(task_id)
        self._update_field(item_id, "Status", {
            "singleSelectOptionId": self._status_option_ids[status.value],
        })

    def add_comment(self, task_id: str, body: str) -> None:
        self._repo_obj.get_issue(int(task_id)).create_comment(body)
