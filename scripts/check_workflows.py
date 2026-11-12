#!/usr/bin/env python3
"""Static checks of the deploy and rollback workflows. No network, no credentials.

    python scripts/check_workflows.py

Three rules, each a failure that would otherwise show up only in a live deploy:

1. **No deploy names its revision.** `gcloud run services update` (or `gcloud run deploy`)
   with --tag or --revision-suffix writes the new revision's name into the service's
   template. The service is managed with OpenTofu alongside kphutt.com's infrastructure,
   and its next template change would resend that name; Cloud Run refuses a second
   revision under an existing name (409). So the deploy creates the revision unnamed and
   tags it afterwards with `update-traffic --update-tags`, which this allows.

2. **No registry command the deployer cannot run.** The deployer holds
   roles/artifactregistry.writer: it can push and create or move tags, but not delete tags
   or images. `gcloud artifacts docker tags add` on an existing tag deletes and recreates
   it, so it would fail after the first deploy, once traffic had already moved.

3. **Every action is pinned to a full commit SHA**, never a tag or branch, which can be
   moved to other code after review. Dependabot keeps the pins current.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"
# Files that run registry commands as the deployer.
DEPLOY_FILES = [".github/workflows/ci.yml", ".github/workflows/rollback.yml", "scripts/move_live_tag.py"]

NAMES_REVISION = re.compile(r"gcloud\s+(?:(?:alpha|beta)\s+)?run\s+(?:services\s+update|deploy)\s(?=.*--(?:tag|revision-suffix)\b)")
NEEDS_DELETE = re.compile(
    r"artifacts\s+docker\s+tags\s+(?:add|delete)|artifacts\s+tags\s+delete"
    r"|artifacts\s+(?:docker\s+images|versions|packages)\s+delete"
)
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)", re.M)
PINNED = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")


def code_lines(text: str, python: bool = False) -> list[tuple[int, str]]:
    """The lines a check should read: comments skipped, shell continuations folded."""
    if python:
        # Skip the module docstring, which explains the command it avoids. Python code
        # passes commands as lists, so join its string items into one line.
        doc = ast.get_docstring(ast.parse(text), clean=False) or ""
        text = text.replace(doc, "", 1)
        text = re.sub(r'",\s*"', " ", text)
    else:
        text = re.sub(r"\\\n\s*", " ", text)
    return [(n, line) for n, line in enumerate(text.splitlines(), 1) if not line.lstrip().startswith("#")]


def problems(repo: Path = REPO) -> list[str]:
    found = []
    for name in DEPLOY_FILES:
        path = repo / name
        if not path.is_file():
            found.append(f"{name}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        for n, line in code_lines(text, python=name.endswith(".py")):
            if NAMES_REVISION.search(line):
                found.append(f"{name}:{n}: a deploy names the revision (--tag or --revision-suffix): {line.strip()}")
            if NEEDS_DELETE.search(line):
                found.append(f"{name}:{n}: needs a delete permission the deployer does not have: {line.strip()}")
    for path in sorted((repo / ".github" / "workflows").glob("*.y*ml")):
        for ref in USES.findall(path.read_text(encoding="utf-8")):
            if not ref.startswith("./") and not PINNED.match(ref):
                found.append(f".github/workflows/{path.name}: action {ref} is not pinned to a full commit SHA")
    return found


def main() -> int:
    found = problems()
    if found:
        print(f"Workflow check FAILED ({len(found)} problem(s)):")
        for f in found:
            print(f"  - {f}")
        return 1
    print("Workflow check passed: no deploy names its revision, no registry command needs a delete")
    print("permission, and every action is pinned to a commit SHA.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
