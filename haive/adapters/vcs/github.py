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
        try:
            self._repo_obj.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=source.commit.sha,
            )
        except github.GithubException as exc:
            if exc.status != 422:  # 422 = branch already exists remotely — reuse it
                raise

        # create_git_ref only creates the branch on GitHub. Without a matching
        # local branch, push_commits()'s git commands would run against
        # whatever happens to be checked out, not this task's branch.
        try:
            subprocess.run(
                ["git", "checkout", "-B", branch_name, base_branch],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"git command failed: {e.cmd}\nstdout: {e.stdout}\nstderr: {e.stderr}"
            ) from e

    def push_commits(self, branch: str, changed_files: list[str], message: str) -> None:
        try:
            # Reset the index first: `git add -- changed_files` only guarantees
            # those files get staged, not that nothing *else* is staged. Without
            # this, anything already in the index from unrelated prior activity
            # would be committed here too, regardless of changed_files.
            subprocess.run(["git", "reset"], check=True, capture_output=True)
            subprocess.run(["git", "add", "--"] + changed_files, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", branch], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"git command failed: {e.cmd}\nstdout: {e.stdout}\nstderr: {e.stderr}"
            ) from e

    def checkout_branch(self, branch_name: str) -> None:
        """Return the local working directory to branch_name and sync with origin.

        Called after a task's PR is fully handled, so the next task (or the
        wave summary) sees a clean, up-to-date base rather than staying on
        the just-finished task's branch. Best-effort: enablePullRequestAutoMerge
        is asynchronous, so this pull may not include this task's own merge
        yet, though it will include any earlier task's completed merge.
        """
        try:
            subprocess.run(["git", "checkout", branch_name], check=True, capture_output=True)
            subprocess.run(["git", "pull", "origin", branch_name], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"git command failed: {e.cmd}\nstdout: {e.stdout}\nstderr: {e.stderr}"
            ) from e

    def create_pr(self, title: str, body: str, head_branch: str, base_branch: str) -> str:
        try:
            pr = self._repo_obj.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch,
            )
        except github.GithubException as exc:
            raise RuntimeError(f"Failed to create PR ({head_branch} -> {base_branch}): {exc}") from exc
        return str(pr.number)

    def merge_pr(self, pr_id: str) -> None:
        """Merge a PR immediately if possible, else enable auto-merge for later.

        A repo with no required status checks makes every PR immediately
        mergeable ("clean" state) — GitHub's enablePullRequestAutoMerge
        mutation rejects those with "Pull request is in clean status", since
        auto-merge exists only to wait on pending checks. Trying a direct
        merge first handles that common case; falling back to enabling
        auto-merge still covers repos where checks are pending.
        """
        pr = self._repo_obj.get_pull(int(pr_id))
        try:
            pr.merge(merge_method="squash")
            return
        except github.GithubException as direct_merge_exc:
            direct_merge_message = str(direct_merge_exc.data.get("message", direct_merge_exc))

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
        except RuntimeError as enable_exc:
            raise RuntimeError(
                f"Direct merge failed ({direct_merge_message}); "
                f"enabling auto-merge also failed ({enable_exc})"
            ) from enable_exc

    def add_pr_comment(self, pr_id: str, body: str) -> None:
        self._repo_obj.get_pull(int(pr_id)).create_issue_comment(body)

    def create_project_pr(self, head_branch: str, base_branch: str, title: str, body: str) -> str:
        return self.create_pr(title, body, head_branch, base_branch)

    def is_pr_merged(self, pr_id: str) -> bool:
        return self._repo_obj.get_pull(int(pr_id)).merged

    def list_task_branches(self, prefix: str) -> list[str]:
        return [b.name for b in self._repo_obj.get_branches() if b.name.startswith(prefix)]

    def find_pr_for_branch(self, branch_name: str) -> tuple[str, bool] | None:
        """Returns (pr_number, merged) for the first PR (any state) with this head branch, or None."""
        owner = self._repo_obj.owner.login
        pulls = self._repo_obj.get_pulls(state="all", head=f"{owner}:{branch_name}")
        for pr in pulls:
            return (str(pr.number), pr.merged)
        return None

    def delete_branch(self, branch_name: str) -> None:
        self._repo_obj.get_git_ref(f"heads/{branch_name}").delete()
