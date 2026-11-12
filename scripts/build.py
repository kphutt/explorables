#!/usr/bin/env python3
"""Build the directory the image serves: pages/ without its READMEs or readable sources,
plus a robots.txt, a sitemap.xml and an llms.txt.

    python scripts/build.py [OUT]     # OUT defaults to public/

Two things in pages/ are for the repository and are never served, so they are left out here:

  - every README.md;
  - each explorable's src/ folder (pages/<slug>/src/). None exists: pages are served as
    written (docs/decisions/0002-serve-readable-source.md). The exclusion stays so that a
    build step brought back later starts with its sources already kept out, and
    scripts/check.py fails if a src/ folder reaches the output anyway.

Nothing else is changed or dropped: a stray file is copied as it is, and scripts/check.py
fails on it, rather than vanishing quietly. OUT is emptied first, so a file deleted from
pages/ cannot outlive it in a working tree.

robots.txt, sitemap.xml and llms.txt are generated, never written by hand, so a new
explorable is in all three the moment its folder exists. The sitemap lists the landing page
and each explorable's index.html (pages/<slug>/index.html), by absolute URL on ORIGIN, each
with the date of the last commit that changed it, when git can say. llms.txt
(https://llmstxt.org/) is a plain-text index for language models: who made these pages, the
author's profiles, and each explorable's title and description, read from its page.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "pages"
DEFAULT_OUT = REPO / "public"

# The origin these pages are served from. Its domain mapping is managed with kphutt.com's
# other infrastructure, outside this repository.
ORIGIN = "https://explorables.kphutt.com"

GENERATED = ("robots.txt", "sitemap.xml", "llms.txt")

# The readable-source folder of an explorable: pages/<slug>/src/.
SOURCES = "src"

# pages/assets/: files several pages share, such as the fonts. Not an explorable, so it is
# not in the sitemap, and it needs no index.html or README.md. scripts/check.py fails if it
# holds a page.
SHARED = "assets"


def is_readme(name: str) -> bool:
    return name.lower() == "readme.md"


def page_paths(source: Path) -> list[str]:
    """The URL path of every page the sitemap lists: the landing page, then each explorable."""
    slugs = sorted(p.name for p in source.iterdir()
                   if p.is_dir() and p.name != SHARED and (p / "index.html").is_file())
    return ["/"] + [f"/{slug}/" for slug in slugs]


# The author, as kphutt.com describes him. AUTHOR_ID is the @id of kphutt.com's Person
# record. Every page's JSON-LD names its author by that @id, so search and answer engines
# join this site's work to the same person. PROFILES is the same list as kphutt.com's
# params.schema.sameAs, and the pages' JSON-LD repeats it.
AUTHOR = "Karsten Huttelmaier"
AUTHOR_HANDLE = "kphutt"
AUTHOR_LINE = "I build identity and security infrastructure."
AUTHOR_URL = "https://kphutt.com/"
AUTHOR_ID = "https://kphutt.com/#person"
PROFILES = {
    "GitHub": "https://github.com/kphutt",
    "LinkedIn": "https://www.linkedin.com/in/karstenhuttelmaier",
    "Stack Overflow": "https://stackoverflow.com/users/165112/kphutt",
    "X": "https://x.com/kphutt",
}

# A commit date as git prints it with --format=%cI.
GIT_DATE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)")


def robots_txt() -> str:
    # Every crawler is welcome, for every use: search, live AI answers and AI training. The
    # Content-Signal line says so in Cloudflare's Content Signals format
    # (contentsignals.org); crawlers that do not know it ignore it (RFC 9309). To stop AI
    # training, set ai-train=no. kphutt.com's robots.txt states the same policy.
    return ("User-agent: *\n"
            "Content-Signal: search=yes, ai-input=yes, ai-train=yes\n"
            "Allow: /\n"
            f"\nSitemap: {ORIGIN}/sitemap.xml\n")


def page_files(source: Path, path: str) -> list[Path]:
    """The files that make up a page: the landing page's own two, or an explorable's folder."""
    if path == "/":
        return [source / "index.html", source / "index.css"]
    return [source / path.strip("/")]


def last_changed(files: list[Path]) -> str:
    """The date of the last commit that touched any of files, or "" if git cannot say."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", *[str(f) for f in files]],
                             cwd=REPO, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    stamp = out.stdout.strip() if out.returncode == 0 else ""
    return stamp if GIT_DATE.fullmatch(stamp) else ""


def sitemap_xml(paths: list[str], lastmods: dict | None = None) -> str:
    lastmods = lastmods or {}

    def entry(path: str) -> str:
        mod = lastmods.get(path)
        stamp = f"<lastmod>{mod}</lastmod>" if mod else ""
        return f"  <url><loc>{escape(ORIGIN + path)}</loc>{stamp}</url>\n"

    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{''.join(entry(p) for p in paths)}</urlset>\n")


def page_summary(page: Path) -> tuple[str, str]:
    """A page's <title> and meta description, as plain text."""
    text = page.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    desc = re.search(r"""<meta\s+name=["']description["']\s+content=["']([^"']*)["']""", text, re.I)

    def clean(m) -> str:
        return " ".join(html.unescape(m.group(1)).split()) if m else ""

    return clean(title), clean(desc)


def llms_txt(source: Path, paths: list[str]) -> str:
    _, summary = page_summary(source / "index.html")
    lines = [
        "# Explorables",
        "",
        f"> {summary}",
        "",
        f"Made by {AUTHOR} ({AUTHOR_HANDLE}). In his words: \"{AUTHOR_LINE}\" About him: {AUTHOR_URL}",
        "",
        "## Profiles",
        "",
        *[f"- [{name}]({url})" for name, url in PROFILES.items()],
        "",
        "## Explorables",
        "",
    ]
    for path in paths:
        if path == "/":
            continue
        title, desc = page_summary(source / path.strip("/") / "index.html")
        lines.append(f"- [{title}]({ORIGIN}{path})" + (f": {desc}" if desc else ""))
    return "\n".join(lines) + "\n"


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
    paths = page_paths(source)
    lastmods = {path: last_changed(page_files(source, path)) for path in paths}
    (out / "sitemap.xml").write_text(sitemap_xml(paths, lastmods), encoding="utf-8", newline="\n")
    (out / "llms.txt").write_text(llms_txt(source, paths), encoding="utf-8", newline="\n")


def main() -> int:
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUT
    if not SOURCE.is_dir():
        sys.exit(f"FAIL: {SOURCE} not found")
    build(SOURCE, out)
    print(f"Built {out.name}/ from pages/ (READMEs and src/ left out, robots.txt, sitemap.xml and llms.txt generated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
