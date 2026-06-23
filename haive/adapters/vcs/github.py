from __future__ import annotations

import subprocess
from typing import Any

import github
import requests

from haive.models.config import Settings

_GRAPHQL_URL = "https://api.github.com/graphql"


class GitHubVCSAdapter:
    def __init__(self, settings: Settings) -> None:
        if not settings.github_token:
            raise ValueError("GitHubVCSAdapter requires GITHUB_TOKEN in settings.")
        if not settings.github_repo:
            raise ValueError("GitHubVCSAdapter requires GITHUB_REPO in settings.")
        if "/" not in settings.github_repo:
            raise ValueError(
                f"GITHUB_REPO must be in 'owner/repo' format, got: {settings.github_repo!r}"
            )
        self._token = settings.github_token
        self._gh = github.Github(settings.github_token)
        self._repo_obj = self._gh.get_repo(settings.github_repo)

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

    def create_branch(self, branch_name: str, base_branch: str) -> None:
        source = self._repo_obj.get_branch(base_branch)
        self._repo_obj.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=source.commit.sha,
        )

    def push_commits(self, branch: str, changed_files: list[str], message: str) -> None:
        try:
            subprocess.run(["git", "add", "--"] + changed_files, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", branch], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"git command failed: {e.cmd}\nstdout: {e.stdout}\nstderr: {e.stderr}"
            ) from e

    def create_pr(self, title: str, body: str, head_branch: str, base_branch: str) -> str:
        pr = self._repo_obj.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=base_branch,
        )
        return str(pr.number)

    def merge_pr(self, pr_id: str) -> None:
        pr = self._repo_obj.get_pull(int(pr_id))
        pr_node_id: str = pr.raw_data["node_id"]
        mutation = """
        mutation($pullRequestId: ID!) {
          enablePullRequestAutoMerge(input: {
            pullRequestId: $pullRequestId
            mergeMethod: SQUASH
          }) { pullRequest { number } }
        }
        """
        try:
            self._graphql(mutation, {"pullRequestId": pr_node_id})
        except RuntimeError:
            pr.merge(merge_method="squash")

    def add_pr_comment(self, pr_id: str, body: str) -> None:
        self._repo_obj.get_pull(int(pr_id)).create_issue_comment(body)

    def create_project_pr(self, head_branch: str, base_branch: str, title: str, body: str) -> str:
        return self.create_pr(title, body, head_branch, base_branch)
