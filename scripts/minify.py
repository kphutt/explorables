#!/usr/bin/env python3
"""Minify one explorable's readable sources into a folder.

    python scripts/minify.py pages/<slug>/src OUT

Every file under SRC is written to the same relative path under OUT:

  - .js: terser, `--compress passes=2 --mangle --ecma 2017 --comments false`;
  - .css: comments removed, whitespace collapsed, and the spaces around `{ } ; , >`
    dropped, then the last `;` before each `}`. Not around `:`, which would break a
    selector like `a :hover`, and not around `+`;
  - .html: each newline and its indent becomes one newline, and blank lines go. Browsers
    render that the same;
  - anything else: copied as it is.

Nothing is renamed across files and no markup is restructured. terser is the one in
node_modules/, installed with `npm ci` from package-lock.json (scripts/check_minify.py does
that in a clean copy). It runs as `node node_modules/terser/bin/terser`, the same entry point
on every system, rather than through the shell wrapper in node_modules/.bin.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

TERSER_ARGS = ["--compress", "passes=2", "--mangle", "--ecma", "2017", "--comments", "false"]


def css(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([{};,>])\s*", r"\1", text)
    return text.replace(";}", "}").strip() + "\n"


def html(text: str) -> str:
    text = re.sub(r"\n[ \t]+", "\n", text)
    return re.sub(r"\n{2,}", "\n", text)


def terser(node_modules: Path, source: Path, out: Path) -> None:
    node = shutil.which("node")
    if not node:
        sys.exit("FAIL: node is not on PATH (the pin is in mise.toml: mise exec -- python ...)")
    entry = node_modules / "terser" / "bin" / "terser"
    if not entry.is_file():
        sys.exit(f"FAIL: {entry} not found -- run `npm ci` first")
    subprocess.run([node, str(entry), str(source), *TERSER_ARGS, "-o", str(out)], check=True)


def minify(src: Path, out: Path, node_modules: Path) -> list[Path]:
    """Write the minified copy of every file under src to out. Returns the paths written, relative to out."""
    written = []
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".js":
            terser(node_modules, path, target)
        elif path.suffix == ".css":
            target.write_text(css(path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
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
