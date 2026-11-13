#!/usr/bin/env python3
"""This repository's GitHub settings, as code rather than clicks.

    python scripts/harden_github.py --dry-run    # print every call, send nothing
    python scripts/harden_github.py              # converge the settings
    python scripts/harden_github.py --check      # read the live settings, report drift, change nothing
    python scripts/harden_github.py --with-socket  # also require Socket's two PR checks

Needs the `gh` CLI, signed in as an admin of the repository. Standard library only. Safe to
re-run: every call sets a value rather than adding one. Each setting is applied on its own,
so one that fails does not stop the rest, and the exit code is non-zero if any failed.

The deploy environment (`cloud-run`) and the repository variables are not here. They name
Google Cloud resources, so they are set from the infrastructure that creates those.

Only add --with-socket once Socket has posted both checks on a real pull request here
(`gh pr checks <number>`). A required check that never reports blocks every pull request.
"""

from __future__ import annotations

import json
import subprocess
import sys

REPO = "kphutt/explorables"
BRANCH = "main"

# The one workflow job that reports on every pull request (.github/workflows/ci.yml). The
# deploy job is skipped on pull requests, so it can never be a required check.
REQUIRED_CHECKS = ["ci"]
SOCKET_CHECKS = ["Socket Security: Project Report", "Socket Security: Pull Request Alerts"]

# Third-party actions the workflows use. GitHub's own actions (actions/*) are allowed too.
ALLOWED_ACTIONS = ["google-github-actions/auth@*", "google-github-actions/setup-gcloud@*"]

SETTINGS = {
    # Squash only, with the PR's own title and body as the commit message, so GitHub adds no
    # trailer of its own (AGENTS.md, "Git attribution").
    "allow_squash_merge": True,
    "allow_merge_commit": False,
    "allow_rebase_merge": False,
    "allow_auto_merge": False,
    "squash_merge_commit_title": "PR_TITLE",
    "squash_merge_commit_message": "PR_BODY",
    "delete_branch_on_merge": True,
    "has_wiki": False,
    "has_projects": False,
    "description": "Interactive explainers you can play with, starting with a backup-power storm test",
    "homepage": "https://explorables.kphutt.com",
}

TOPICS = ["explorable-explanations", "interactive", "static-site", "cloud-run"]


def protection(with_socket: bool) -> dict:
    return {
        "required_status_checks": {"strict": True, "contexts": REQUIRED_CHECKS + (SOCKET_CHECKS if with_socket else [])},
        # Admins too: the owner's own pushes go through a reviewed pull request like any other.
        "enforce_admins": True,
        # A pull request is required, with zero approvals: a sole owner cannot approve their
        # own pull request, so any count above zero would block every merge.
        "required_pull_request_reviews": {
            "required_approving_review_count": 0,
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
        },
        "restrictions": None,
        "required_conversation_resolution": True,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def calls(with_socket: bool) -> list[tuple[str, list[str], dict | None]]:
    r = f"repos/{REPO}"
    return [
        ("merge settings, description and homepage", ["-X", "PATCH", r], SETTINGS),
        ("topics", ["-X", "PUT", f"{r}/topics"], {"names": TOPICS}),
        ("Actions token read-only, and it cannot approve pull requests",
         ["-X", "PUT", f"{r}/actions/permissions/workflow"],
         {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False}),
        ("Actions limited to selected actions", ["-X", "PUT", f"{r}/actions/permissions"],
         {"enabled": True, "allowed_actions": "selected"}),
        ("the selected actions", ["-X", "PUT", f"{r}/actions/permissions/selected-actions"],
         {"github_owned_allowed": True, "verified_allowed": False, "patterns_allowed": ALLOWED_ACTIONS}),
        ("workflows from outside contributors' forks wait for approval",
         ["-X", "PUT", f"{r}/actions/permissions/fork-pr-contributor-approval"],
         {"approval_policy": "all_external_contributors"}),
        ("Dependabot alerts", ["-X", "PUT", f"{r}/vulnerability-alerts"], None),
        ("Dependabot security updates", ["-X", "PUT", f"{r}/automated-security-fixes"], None),
        ("private vulnerability reporting (SECURITY.md points here)",
         ["-X", "PUT", f"{r}/private-vulnerability-reporting"], None),
        ("secret scanning and push protection", ["-X", "PATCH", r],
         {"security_and_analysis": {"secret_scanning": {"status": "enabled"},
                                    "secret_scanning_push_protection": {"status": "enabled"}}}),
        (f"branch protection on {BRANCH}", ["-X", "PUT", f"{r}/branches/{BRANCH}/protection"], protection(with_socket)),
    ]


def gh(args: list[str], body: dict | None = None) -> tuple[bool, str]:
    cmd = ["gh", "api", *args]
    if body is not None:
        cmd += ["--input", "-"]
    result = subprocess.run(cmd, input=None if body is None else json.dumps(body), capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def check(with_socket: bool) -> int:
    """Read the live settings and report every difference from the ones above."""
    drift = []
    ok, out = gh([f"repos/{REPO}"])
    if not ok:
        print(f"could not read {REPO}: {out}")
        return 2
    live = json.loads(out)
    for key, want in SETTINGS.items():
        if live.get(key) != want:
            drift.append(f"{key} is {live.get(key)!r}, want {want!r}")
    for key in ("secret_scanning", "secret_scanning_push_protection"):
        got = ((live.get("security_and_analysis") or {}).get(key) or {}).get("status")
        if got != "enabled":
            drift.append(f"{key} is {got!r}, want 'enabled'")
    ok, out = gh([f"repos/{REPO}/actions/permissions/workflow"])
    if ok and json.loads(out).get("default_workflow_permissions") != "read":
        drift.append("the default Actions token is not read-only")
    ok, out = gh([f"repos/{REPO}/branches/{BRANCH}/protection"])
    if not ok:
        drift.append(f"no branch protection on {BRANCH}")
    else:
        live_protection = json.loads(out)
        contexts = sorted((live_protection.get("required_status_checks") or {}).get("contexts") or [])
        want = sorted(protection(with_socket)["required_status_checks"]["contexts"])
        if contexts != want:
            drift.append(f"required checks are {contexts}, want {want}")
        for key in ("enforce_admins", "required_conversation_resolution", "required_linear_history"):
            if not (live_protection.get(key) or {}).get("enabled"):
                drift.append(f"{key} is off")
        if (live_protection.get("allow_force_pushes") or {}).get("enabled"):
            drift.append("force pushes are allowed")
    for message in drift:
        print(f"drift: {message}")
    print("no drift" if not drift else f"{len(drift)} setting(s) differ")
    return 1 if drift else 0


def main() -> int:
    args = set(sys.argv[1:])
    unknown = args - {"--dry-run", "--check", "--with-socket"}
    if unknown:
        sys.exit(__doc__)
    with_socket = "--with-socket" in args
    if "--check" in args:
        return check(with_socket)
    failed = 0
    for label, api, body in calls(with_socket):
        shown = f"gh api {' '.join(api)}" + (f" --input - <<< '{json.dumps(body)}'" if body is not None else "")
        if "--dry-run" in args:
            print(f"would set {label}:\n  {shown}")
            continue
        ok, out = gh(api, body)
        print(f"[{'ok' if ok else 'FAILED'}] {label}" + ("" if ok else f": {out}"))
        failed += not ok
    if failed:
        print(f"\n{failed} setting(s) did not apply. Fix the cause and run this again.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
