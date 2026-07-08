from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests

from haive.models.enums import AgentRole, Complexity, TaskStatus

_GRAPHQL_URL = "https://api.github.com/graphql"


def _option(name: str, color: str, description: str = "") -> dict[str, str]:
    return {"name": name, "color": color, "description": description}


# Colors are cosmetic only — chosen to spread values visually across the
# GitHub UI's palette, not semantically meaningful to haive itself.
_AGENT_ROLE_COLORS: dict[str, str] = {
    AgentRole.SCAFFOLD_AGENT.value: "GRAY",
    AgentRole.IMPLEMENTATION_AGENT.value: "BLUE",
    AgentRole.CODE_EDITOR_AGENT.value: "BLUE",
    AgentRole.REFACTORING_AGENT.value: "PURPLE",
    AgentRole.API_INTEGRATION_AGENT.value: "ORANGE",
    AgentRole.DATABASE_AGENT.value: "ORANGE",
    AgentRole.TEST_GENERATOR_AGENT.value: "GREEN",
    AgentRole.CODE_REVIEWER_AGENT.value: "YELLOW",
    AgentRole.SECURITY_REVIEWER_AGENT.value: "RED",
    AgentRole.DOCUMENTATION_WRITER_AGENT.value: "PINK",
}

_COMPLEXITY_COLORS: dict[str, str] = {
    Complexity.LOW.value: "GREEN",
    Complexity.MEDIUM.value: "YELLOW",
    Complexity.HIGH.value: "RED",
}

_STATUS_COLORS: dict[str, str] = {
    TaskStatus.PENDING.value: "GRAY",
    TaskStatus.IN_PROGRESS.value: "YELLOW",
    TaskStatus.COMPLETE.value: "GREEN",
    TaskStatus.NEEDS_HUMAN_REVIEW.value: "ORANGE",
    TaskStatus.AWAITING_MERGE.value: "BLUE",
    TaskStatus.BLOCKED.value: "RED",
    TaskStatus.SKIPPED.value: "PURPLE",
}

# Haive spec: six required custom fields, exact names — sourced from the
# same enums haive itself validates against (haive/models/enums.py), so
# these can never silently drift out of sync with what GitHubPMAdapter
# actually requires.
_CUSTOM_FIELDS: list[tuple[str, str, list[dict[str, str]] | None]] = [
    ("haive_agent_role", "SINGLE_SELECT", [_option(r.value, _AGENT_ROLE_COLORS[r.value]) for r in AgentRole]),
    ("haive_complexity", "SINGLE_SELECT", [_option(c.value, _COMPLEXITY_COLORS[c.value]) for c in Complexity]),
    ("haive_depends_on", "TEXT", None),
    ("haive_lineage_depth", "NUMBER", None),
    ("haive_recovery_for", "TEXT", None),
    ("haive_acceptance_criteria", "TEXT", None),
]

_STATUS_OPTIONS = [_option(s.value, _STATUS_COLORS[s.value]) for s in TaskStatus]


@dataclass
class BoardSetupResult:
    project_number: int
    project_url: str
    created_project: bool
    fields_created: list[str] = field(default_factory=list)
    fields_already_existing: list[str] = field(default_factory=list)
    status_updated: bool = False
    verified: bool = False
    verification_issues: list[str] = field(default_factory=list)


def _graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(
        _GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GitHub GraphQL error: {data['errors']}")
    return data["data"]


def _find_or_create_project(
    token: str, owner: str, repo: str, title: str
) -> tuple[dict[str, Any], str, bool]:
    """Returns (project, repo_node_id, created). Reuses an open project with
    the same title if one already exists, rather than creating a duplicate.
    """
    data = _graphql(
        token,
        """
        query($owner: String!, $repo: String!) {
          repositoryOwner(login: $owner) {
            id
            ... on User { projectsV2(first: 100) { nodes { id title number url closed } } }
            ... on Organization { projectsV2(first: 100) { nodes { id title number url closed } } }
          }
          repository(owner: $owner, name: $repo) { id }
        }
        """,
        {"owner": owner, "repo": repo},
    )
    if not data["repository"]:
        raise RuntimeError(f"Repository {owner}/{repo} not found (or token lacks access).")
    owner_id = data["repositoryOwner"]["id"]
    repo_id = data["repository"]["id"]

    existing = [
        p for p in data["repositoryOwner"].get("projectsV2", {}).get("nodes", [])
        if p and p["title"] == title and not p["closed"]
    ]
    if existing:
        return existing[0], repo_id, False

    project = _graphql(
        token,
        """
        mutation($ownerId: ID!, $title: String!) {
          createProjectV2(input: {ownerId: $ownerId, title: $title}) {
            projectV2 { id title number url }
          }
        }
        """,
        {"ownerId": owner_id, "title": title},
    )["createProjectV2"]["projectV2"]
    return project, repo_id, True


def _link_project(token: str, project_id: str, repo_id: str) -> None:
    _graphql(
        token,
        """
        mutation($projectId: ID!, $repoId: ID!) {
          linkProjectV2ToRepository(input: {projectId: $projectId, repositoryId: $repoId}) {
            repository { nameWithOwner }
          }
        }
        """,
        {"projectId": project_id, "repoId": repo_id},
    )


def _fetch_fields(token: str, project_id: str) -> dict[str, dict[str, Any]]:
    nodes = _graphql(
        token,
        """
        query($id: ID!) {
          node(id: $id) {
            ... on ProjectV2 {
              fields(first: 50) {
                nodes {
                  ... on ProjectV2FieldCommon { id name dataType }
                  ... on ProjectV2SingleSelectField { options { name } }
                }
              }
            }
          }
        }
        """,
        {"id": project_id},
    )["node"]["fields"]["nodes"]
    return {n["name"]: n for n in nodes if n}


def _create_custom_fields(token: str, project_id: str) -> tuple[list[str], list[str]]:
    """Returns (created, already_existing) field names."""
    fields = _fetch_fields(token, project_id)
    created: list[str] = []
    already_existing: list[str] = []
    for name, dtype, options in _CUSTOM_FIELDS:
        if name in fields:
            already_existing.append(name)
            continue
        variables: dict[str, Any] = {"projectId": project_id, "dataType": dtype, "name": name}
        if dtype == "SINGLE_SELECT":
            query = """
              mutation($projectId: ID!, $dataType: ProjectV2CustomFieldType!, $name: String!,
                       $options: [ProjectV2SingleSelectFieldOptionInput!]) {
                createProjectV2Field(input: {projectId: $projectId, dataType: $dataType,
                                             name: $name, singleSelectOptions: $options}) {
                  projectV2Field { ... on ProjectV2FieldCommon { name } }
                }
              }
            """
            variables["options"] = options
        else:
            query = """
              mutation($projectId: ID!, $dataType: ProjectV2CustomFieldType!, $name: String!) {
                createProjectV2Field(input: {projectId: $projectId, dataType: $dataType, name: $name}) {
                  projectV2Field { ... on ProjectV2FieldCommon { name } }
                }
              }
            """
        _graphql(token, query, variables)
        created.append(name)
    return created, already_existing


def _configure_status(token: str, project_id: str) -> bool:
    """Returns True if Status options were updated, False if already correct
    or the built-in Status field couldn't be found.
    """
    fields = _fetch_fields(token, project_id)
    status = fields.get("Status")
    if not status:
        return False
    wanted = [o["name"] for o in _STATUS_OPTIONS]
    current = [o["name"] for o in status.get("options", [])]
    if current == wanted:
        return False
    _graphql(
        token,
        """
        mutation($fieldId: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
          updateProjectV2Field(input: {fieldId: $fieldId, singleSelectOptions: $options}) {
            projectV2Field { ... on ProjectV2FieldCommon { name } }
          }
        }
        """,
        {"fieldId": status["id"], "options": _STATUS_OPTIONS},
    )
    return True


def _verify(token: str, project_id: str) -> list[str]:
    """Returns a list of verification issues; empty means everything checks out."""
    fields = _fetch_fields(token, project_id)
    issues: list[str] = []
    for name, _dtype, options in _CUSTOM_FIELDS + [("Status", "SINGLE_SELECT", _STATUS_OPTIONS)]:
        f = fields.get(name)
        if not f:
            issues.append(f"missing field: {name}")
            continue
        if options:
            got = [o["name"] for o in f.get("options", [])]
            want = [o["name"] for o in options]
            if got != want:
                issues.append(f"{name} options mismatch: got {got}, want {want}")
    return issues


def setup_board(token: str, owner: str, repo: str, title: str) -> BoardSetupResult:
    """Create (or reuse) a Haive-compatible GitHub Project v2 board for a repo.

    Idempotent: safe to call again against an already-configured board —
    existing fields and correct Status options are left untouched.
    """
    project, repo_id, created = _find_or_create_project(token, owner, repo, title)
    _link_project(token, project["id"], repo_id)
    fields_created, fields_already_existing = _create_custom_fields(token, project["id"])
    status_updated = _configure_status(token, project["id"])
    issues = _verify(token, project["id"])

    return BoardSetupResult(
        project_number=project["number"],
        project_url=project["url"],
        created_project=created,
        fields_created=fields_created,
        fields_already_existing=fields_already_existing,
        status_updated=status_updated,
        verified=not issues,
        verification_issues=issues,
    )
