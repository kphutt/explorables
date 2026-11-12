#!/usr/bin/env python3
"""Run the CI gate locally, on the same terms CI runs it.

Run by pre-commit at the pre-push stage (.pre-commit-config.yaml). It adds no checks of its
own: it runs the commands of the `ci` job in .github/workflows/ci.yml, in the same order:

    python3 scripts/build.py
    python3 scripts/check.py public
    python3 scripts/check_workflows.py
    python3 -m unittest discover -s scripts -p "test_*.py"

The secret scan runs at the pre-commit stage instead (gitleaks, in the same config). The
container build and smoke test need Docker; with --smoke URL it runs scripts/smoke.py
against a copy already running there, such as `docker run --rm -p 8080:8080 --read-only
explorables` or static-web-server started on public/ with server/sws.toml.

What it does add is CI's precondition, a clean output directory: CI builds into a fresh
checkout, and scripts/build.py empties public/ first, so a file deleted from pages/ cannot
outlive it here.

    python scripts/local_verify.py
    python scripts/local_verify.py --smoke http://127.0.0.1:8080
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run(cmd: list[str], label: str) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    if subprocess.run(cmd, cwd=REPO).returncode != 0:
        print(f"\nlocal gate FAILED: {label}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    args = sys.argv[1:]
    smoke = None
    if args[:1] == ["--smoke"] and len(args) == 2:
        smoke = args[1]
    elif args:
        sys.exit(__doc__)
    py = sys.executable
    run([py, "scripts/build.py"], "build failed")
    run([py, "scripts/check.py", "public"], "build check failed")
    run([py, "scripts/check_workflows.py"], "workflow check failed")
    run([py, "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py"], "unit tests failed")
    if smoke:
        run([py, "scripts/smoke.py", smoke], "smoke test failed")
    print("\nlocal gate passed -- matches the CI ci job" + (" and its smoke test" if smoke else " (no smoke test: pass --smoke URL)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
