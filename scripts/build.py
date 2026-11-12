#!/usr/bin/env python3
"""Build the directory the image serves: pages/ without its READMEs or readable sources,
plus a robots.txt and a sitemap.xml.

    python scripts/build.py [OUT]     # OUT defaults to public/

Two things in pages/ are for the repository and are never served, so they are left out here:

  - every README.md;
  - each explorable's src/ folder (pages/<slug>/src/), the readable sources its served
    files are minified from (scripts/check_minify.py).

Nothing else is changed or dropped: a stray file is copied as it is, and scripts/check.py
fails on it, rather than vanishing quietly. OUT is emptied first, so a file deleted from
pages/ cannot outlive it in a working tree.

robots.txt and sitemap.xml are generated, never written by hand, so a new explorable is in
the sitemap the moment its folder exists. The sitemap lists the landing page and each
explorable's index.html (pages/<slug>/index.html), by absolute URL on ORIGIN.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "pages"
DEFAULT_OUT = REPO / "public"

# The origin these pages are served from. Its domain mapping is managed with kphutt.com's
# other infrastructure, outside this repository.
ORIGIN = "https://explorables.kphutt.com"

GENERATED = ("robots.txt", "sitemap.xml")

# The readable-source folder of an explorable: pages/<slug>/src/.
SOURCES = "src"


def is_readme(name: str) -> bool:
    return name.lower() == "readme.md"


def page_paths(source: Path) -> list[str]:
    """The URL path of every page the sitemap lists: the landing page, then each explorable."""
    slugs = sorted(p.name for p in source.iterdir() if p.is_dir() and (p / "index.html").is_file())
    return ["/"] + [f"/{slug}/" for slug in slugs]


def robots_txt() -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {ORIGIN}/sitemap.xml\n"


def sitemap_xml(paths: list[str]) -> str:
    urls = "".join(f"  <url><loc>{escape(ORIGIN + path)}</loc></url>\n" for path in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}</urlset>\n")


def build(source: Path = SOURCE, out: Path = DEFAULT_OUT) -> None:
    clash = [name for name in GENERATED if (source / name).exists()]
    if clash:
        sys.exit(f"FAIL: {', '.join(clash)} in pages/ -- the build generates these, so delete them")
    if out.exists():
        shutil.rmtree(out)

    def ignore(directory: str, names: list[str]) -> list[str]:
        here = Path(directory).resolve()
        # Only an explorable's own src/ folder, one level below pages/. A folder named src
        # anywhere else is copied, and check.py fails on it.
        is_explorable = here.parent == source.resolve()
        return [n for n in names if is_readme(n) or (is_explorable and n == SOURCES and (here / n).is_dir())]

    shutil.copytree(source, out, ignore=ignore)
    (out / "robots.txt").write_text(robots_txt(), encoding="utf-8", newline="\n")
    (out / "sitemap.xml").write_text(sitemap_xml(page_paths(source)), encoding="utf-8", newline="\n")


def main() -> int:
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUT
    if not SOURCE.is_dir():
        sys.exit(f"FAIL: {SOURCE} not found")
    build(SOURCE, out)
    print(f"Built {out.name}/ from pages/ (READMEs and src/ left out, robots.txt and sitemap.xml generated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
