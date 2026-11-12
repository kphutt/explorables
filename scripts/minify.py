#!/usr/bin/env python3
"""Minify one explorable's readable sources into a folder.

    python scripts/minify.py pages/<slug>/src OUT

Every file under SRC is written to the same relative path under OUT:

  - .js and .css: esbuild, `--minify --target=es2017`. One standard tool for both; the
    target keeps the output to what ES2017 browsers run;
  - .html: each newline and its indent becomes one newline, and blank lines go. Browsers
    render that the same;
  - anything else: copied as it is.

Nothing is bundled, renamed across files or restructured: each file is minified on its own.
esbuild is the one in node_modules/, installed with `npm ci` from package-lock.json
(scripts/check_minify.py does that in a clean copy). It runs as
`node node_modules/esbuild/bin/esbuild`, the same entry point on every system. That shim
starts the platform binary npm installed as an optional dependency (@esbuild/<os>-<cpu>),
so it needs no install script, and .npmrc's ignore-scripts stays on.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ESBUILD_ARGS = ["--minify", "--target=es2017", "--log-level=warning"]


def html(text: str) -> str:
    text = re.sub(r"\n[ \t]+", "\n", text)
    return re.sub(r"\n{2,}", "\n", text)


def esbuild(node_modules: Path, source: Path, out: Path) -> None:
    node = shutil.which("node")
    if not node:
        sys.exit("FAIL: node is not on PATH (the pin is in mise.toml: mise exec -- python ...)")
    entry = node_modules / "esbuild" / "bin" / "esbuild"
    if not entry.is_file():
        sys.exit(f"FAIL: {entry} not found -- run `npm ci` first")
    subprocess.run([node, str(entry), str(source), *ESBUILD_ARGS, f"--outfile={out}"], check=True)


def minify(src: Path, out: Path, node_modules: Path) -> list[Path]:
    """Write the minified copy of every file under src to out. Returns the paths written, relative to out."""
    written = []
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix in (".js", ".css"):
            esbuild(node_modules, path, target)
        elif path.suffix == ".html":
            target.write_text(html(path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
        else:
            shutil.copyfile(path, target)
        written.append(rel)
    return written


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_dir():
        sys.exit(f"FAIL: {src} is not a folder")
    written = minify(src, out, Path(__file__).resolve().parent.parent / "node_modules")
    print({p.as_posix(): (out / p).stat().st_size for p in written})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
