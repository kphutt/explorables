#!/usr/bin/env python3
"""Check that every explorable's served files are exactly what its readable sources minify to.

    python scripts/check_minify.py           # check, change nothing
    python scripts/check_minify.py --write   # rewrite the served files from src/

An explorable may keep readable sources in pages/<slug>/src/. The files served are the
minified ones beside it, pages/<slug>/<same path>, and both are committed. This fails unless
minifying src/ from a clean start gives the committed files byte for byte, so a change made
to one and not the other cannot ship. An explorable without a src/ folder is skipped.

A clean start means: package.json, package-lock.json and .npmrc are copied into an empty
temporary folder, `npm ci` installs exactly the locked versions there, and
scripts/minify.py runs from that install. Nothing in the working tree's node_modules/ is used.

npm is held to the repository's baseline before anything is installed: npm 11.10.0 or newer,
so .npmrc's min-release-age is enforced rather than ignored, and ignore-scripts on, so no
package's install script runs. `npm ci` also gets --ignore-scripts on its command line.

After a terser update changes the output, run with --write, review the diff of the served
files, and commit them with the update.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import minify  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PAGES = REPO / "pages"
NPM_FILES = ("package.json", "package-lock.json", ".npmrc")
MIN_NPM = (11, 10, 0)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def npm() -> str:
    found = shutil.which("npm")
    if not found:
        sys.exit("FAIL: npm is not on PATH (the Node pin is in mise.toml: mise exec -- python scripts/check_minify.py)")
    return found


def npm_out(args: list[str], cwd: Path) -> str:
    return subprocess.run([npm(), *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def require_baseline(cwd: Path) -> None:
    version = npm_out(["-v"], cwd)
    parts = tuple(int(p) for p in re.findall(r"\d+", version)[:3])
    if parts < MIN_NPM:
        sys.exit(f"FAIL: npm {version} is older than {'.'.join(map(str, MIN_NPM))}, which ignores min-release-age. "
                 "Use the Node pinned in mise.toml.")
    ignore = npm_out(["config", "get", "ignore-scripts"], cwd)
    before = npm_out(["config", "get", "before"], cwd)
    if ignore != "true":
        sys.exit(f"FAIL: npm ignore-scripts is {ignore!r}, not true (.npmrc)")
    if before in ("", "null", "undefined"):
        sys.exit("FAIL: npm has no release-age cutoff ('before' is unset), so .npmrc's min-release-age is not in effect")
    print(f"npm {version}, ignore-scripts=true, before={before}")


def explorables_with_sources(pages: Path = PAGES) -> list[Path]:
    return sorted(p for p in pages.iterdir() if p.is_dir() and (p / "src").is_dir())


def compare(slug_dir: Path, built: Path, written: list[Path]) -> list[str]:
    problems = []
    for rel in written:
        served = slug_dir / rel
        where = f"pages/{slug_dir.name}/{rel.as_posix()}"
        if not served.is_file():
            problems.append(f"{where}: missing, but src/{rel.as_posix()} minifies to it")
        elif served.read_bytes() != (built / rel).read_bytes():
            problems.append(f"{where}: sha256 {sha(served)}, but src/{rel.as_posix()} minifies to {sha(built / rel)}")
    return problems


def main() -> int:
    args = sys.argv[1:]
    if args not in ([], ["--write"]):
        sys.exit(__doc__)
    write = args == ["--write"]
    slugs = explorables_with_sources()
    if not slugs:
        print("Minify check: no explorable has a src/ folder, nothing to check")
        return 0
    with tempfile.TemporaryDirectory(prefix="check-minify-") as tmp:
        clean = Path(tmp)
        for name in NPM_FILES:
            shutil.copyfile(REPO / name, clean / name)
        require_baseline(clean)
        print("$ npm ci --ignore-scripts --no-audit --no-fund  (in a clean temporary folder)", flush=True)
        subprocess.run([npm(), "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=clean, check=True)
        problems = []
        checked = 0
        for slug_dir in slugs:
            built = clean / "out" / slug_dir.name
            written = minify.minify(slug_dir / "src", built, clean / "node_modules")
            checked += len(written)
            if write:
                for rel in written:
                    (slug_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(built / rel, slug_dir / rel)
                    print(f"wrote pages/{slug_dir.name}/{rel.as_posix()}")
            else:
                problems += compare(slug_dir, built, written)
    if problems:
        print(f"Minify check FAILED ({len(problems)} problem(s)). Run `python scripts/check_minify.py --write`, "
              "review the diff, and commit the served files with their sources:")
        for p in problems:
            print(f"  - {p}")
        return 1
    if not write:
        print(f"Minify check passed: {checked} file(s) in {len(slugs)} explorable(s) are byte-identical to what "
              "their src/ minifies to, from a clean npm ci.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
