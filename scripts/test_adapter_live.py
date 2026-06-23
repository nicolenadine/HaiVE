#!/usr/bin/env python3
"""
Live smoke test for GitHubPMAdapter.

Usage:
    uv run python scripts/test_adapter_live.py \
        --token  ghp_xxx \
        --repo   owner/repo \
        --project 1 \
        --milestone 1

All four flags are required. No other haive config or Settings fields needed.
"""

import argparse
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

# Minimal settings stand-in — only the fields the adapter actually uses.
def _make_settings(token: str, repo: str, project_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        github_token=token,
        github_repo=repo,
        github_project_id=project_id,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test GitHubPMAdapter against a live repo.")
    parser.add_argument("--token",     required=True, help="GitHub personal access token")
    parser.add_argument("--repo",      required=True, help="owner/repo (e.g. nicolenadine/HaiVE)")
    parser.add_argument("--project",   required=True, type=int, help="GitHub Projects v2 board number")
    parser.add_argument("--milestone", required=True, type=int, help="GitHub milestone number to test against")
    args = parser.parse_args()

    # Late import so the script fails fast on arg errors before loading anything.
    from haive.adapters.pm.github import GitHubPMAdapter

    settings = _make_settings(args.token, args.repo, args.project)

    print(f"\n{'='*60}")
    print(f"  Repo:      {args.repo}")
    print(f"  Project:   {args.project}  (Projects v2 board)")
    print(f"  Milestone: {args.milestone}")
    print(f"{'='*60}\n")

    # ── 1. Startup validation ────────────────────────────────────────────────
    print("[ 1/3 ] Connecting and validating custom fields...")
    try:
        adapter = GitHubPMAdapter(settings)
        print("        ✓ All 6 haive_* custom fields present on the board.\n")
    except RuntimeError as e:
        print(f"        ✗ {e}\n")
        sys.exit(1)
    except ValueError as e:
        print(f"        ✗ Bad settings: {e}\n")
        sys.exit(1)

    # ── 2. get_project ───────────────────────────────────────────────────────
    print(f"[ 2/3 ] get_project(\"{args.milestone}\")...")
    try:
        project = adapter.get_project(str(args.milestone))
        print(f"        title:          {project.title}")
        print(f"        description:    {project.description or '(empty)'}")
        print(f"        project_branch: {project.project_branch}\n")
    except Exception as e:
        print(f"        ✗ {e}\n")
        sys.exit(1)

    # ── 3. get_tasks ─────────────────────────────────────────────────────────
    print(f"[ 3/3 ] get_tasks(\"{args.milestone}\")...")
    try:
        tasks = adapter.get_tasks(str(args.milestone))
        if not tasks:
            print("        (no issues found assigned to this milestone on the board)")
        for t in tasks:
            print(f"        #{t.task_id}  [{t.agent_role.value}]  [{t.complexity.value}]  {t.title}")
            if t.depends_on:
                print(f"               depends_on: {t.depends_on}")
            if t.acceptance_criteria:
                print(f"               criteria:   {t.acceptance_criteria[0][:60]}...")
        print()
    except Exception as e:
        print(f"        ✗ {e}\n")
        sys.exit(1)

    print("Done.\n")


if __name__ == "__main__":
    main()
