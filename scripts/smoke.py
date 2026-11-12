#!/usr/bin/env python3
"""Smoke-test a running copy of explorables.kphutt.com: every page answers, every header is right.

The workflow runs it against the container on the CI runner, and against the Cloud Run
candidate revision before it gets any traffic.

    python scripts/smoke.py http://127.0.0.1:8080
    python scripts/smoke.py https://cand-abc123---explorables-xyz-uw.a.run.app

What it checks, against BASE:
  - the landing page and its stylesheet return 200;
  - robots.txt and sitemap.xml return 200, robots.txt names the sitemap, and every URL the
    sitemap lists returns 200 with no X-Robots-Tag, so it can be found in search;
  - every pages/<slug>/ is in the sitemap, and /<slug> redirects to exactly /<slug>/;
  - every README path is a 404: the READMEs are for the repository and never served. So is
    every file of an explorable's readable sources (pages/<slug>/src/);
  - a missing page returns 404 with pages/404.html, not the server's built-in page;
  - HTML, CSS, JavaScript and SVG come back compressed when the browser asks for it;
  - every one of those responses carries exactly the headers of the catch-all rule in
    server/sws.toml, Cache-Control included. The expected values are read from that file,
    so the config is the one place they are written down.

Standard library only.
"""

from __future__ import annotations

import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import ORIGIN, SOURCES  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "server" / "sws.toml"
SOURCE = REPO / "pages"

USER_AGENT = "explorables-smoke"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D102 -- see a redirect, don't follow it
        return None


OPENER = urllib.request.build_opener(NoRedirect)

# Statuses worth waiting out on a fresh URL: a candidate's tagged hostname can answer 404
# or 5xx from Google's front end for a few seconds after it is created, and a cold
# instance can answer 5xx while it starts.
TRANSIENT = {404, 429, 500, 502, 503, 504}


def fetch(url: str, attempts: int = 1):
    """GET without following redirects. Returns (status, headers, body).

    With attempts > 1, connection errors and TRANSIENT statuses are retried, three seconds
    apart, and the last answer is returned.
    """
    last = None
    for attempt in range(attempts):
        try:
            with OPENER.open(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            last = (e.code, e.headers, e.read())
            if e.code not in TRANSIENT or attempt == attempts - 1:
                return last
        except (urllib.error.URLError, OSError) as e:
            last = e
        time.sleep(3)
    if isinstance(last, tuple):
        return last
    raise SystemExit(f"FAIL: {url} did not answer after {attempts} attempt(s): {last}")


def expected_headers() -> dict:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    for rule in config["advanced"]["headers"]:
        if rule["source"] == "**":
            return dict(rule["headers"])
    sys.exit(f"FAIL: no catch-all '**' header rule in {CONFIG}")


# The server compresses every text type (svg counts, by its +xml suffix) but not woff2, and
# skips bodies under 200 bytes (static-web-server 3.0.0-beta.2, src/compression.rs
# and src/exts/mime.rs). So these are the files to check, and the size below which a file is not.
COMPRESSED_SUFFIXES = (".html", ".css", ".js", ".svg")
MIN_COMPRESS_SIZE = 200


def served(path: Path) -> bool:
    """True for a file under pages/ the build copies: not a README, a dot-file or a source."""
    parts = path.relative_to(SOURCE).parts
    return (path.is_file() and path.name.lower() != "readme.md"
            and not any(part.startswith(".") for part in parts)
            and not (len(parts) > 2 and parts[1] == SOURCES))


def compressed_paths() -> list[str]:
    """URL paths of every file the server should compress, read from pages/."""
    return sorted("/" + p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*")
                  if served(p) and p.suffix in COMPRESSED_SUFFIXES and p.stat().st_size >= MIN_COMPRESS_SIZE)


def source_paths() -> list[str]:
    """URL paths of every readable source file, none of which may be served."""
    return sorted("/" + p.relative_to(SOURCE).as_posix() for p in SOURCE.glob(f"*/{SOURCES}/**/*") if p.is_file())


def content_encoding(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "br, gzip"})
    with urllib.request.urlopen(request, timeout=20) as r:
        return r.headers.get("Content-Encoding") or ""


def slugs() -> list[str]:
    return sorted(p.name for p in SOURCE.iterdir() if p.is_dir() and not p.name.startswith("."))


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    base = sys.argv[1].rstrip("/")
    want = expected_headers()
    failures = []

    def check(path, status=200, content_type=None, attempts=1):
        got, headers, body = fetch(base + path, attempts)
        if got != status:
            failures.append(f"{path}: status {got}, expected {status}")
        if headers.get("X-Robots-Tag") is not None:
            failures.append(f"{path}: X-Robots-Tag {headers.get('X-Robots-Tag')!r}, expected none")
        for name, value in want.items():
            if headers.get(name) != value:
                failures.append(f"{path}: {name} is {headers.get(name)!r}, expected {value!r}")
        if content_type and not (headers.get("Content-Type") or "").startswith(content_type):
            failures.append(f"{path}: Content-Type {headers.get('Content-Type')!r}, expected {content_type}")
        return headers, body

    # A cold instance or a tagged URL still being set up gets about thirty seconds.
    check("/", content_type="text/html", attempts=10)
    check("/index.css", content_type="text/css")
    check("/README.md", status=404, content_type="text/html")

    _, robots = check("/robots.txt", content_type="text/plain")
    if f"Sitemap: {ORIGIN}/sitemap.xml" not in robots.decode("utf-8", "replace").splitlines():
        failures.append(f"/robots.txt has no 'Sitemap: {ORIGIN}/sitemap.xml' line")
    _, sitemap = check("/sitemap.xml", content_type="application/xml")
    try:
        locs = [(e.text or "").strip() for e in ET.fromstring(sitemap).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    except ET.ParseError as e:
        locs = []
        failures.append(f"/sitemap.xml is not valid XML: {e}")
    paths = []
    for loc in locs:
        if not loc.startswith(ORIGIN + "/"):
            failures.append(f"sitemap lists {loc}, which is not under {ORIGIN}")
            continue
        paths.append(loc[len(ORIGIN):])
        check(paths[-1], content_type="text/html")
    if "/" not in paths:
        failures.append("sitemap does not list the landing page")

    found = slugs()
    for slug in found:
        if f"/{slug}/" not in paths:
            failures.append(f"sitemap does not list /{slug}/")
        check(f"/{slug}/README.md", status=404, content_type="text/html")
        got, headers, _ = fetch(f"{base}/{slug}")
        location = headers.get("Location", "")
        if got not in (301, 308) or location != f"/{slug}/":
            failures.append(f"/{slug}: status {got} Location {location!r}, expected a redirect to exactly /{slug}/")

    hidden_sources = source_paths()
    for path in hidden_sources:
        check(path, status=404, content_type="text/html")

    # pages/404.html, not the server's built-in page: its title, stylesheet and noindex, and
    # none of the inline <style> only the built-in page has.
    _, body = check("/this-page-does-not-exist/", status=404, content_type="text/html")
    text = body.decode("utf-8", "replace")
    if ("<title>Not found</title>" not in text or 'href="/index.css"' not in text
            or '<meta name="robots" content="noindex">' not in text or re.search(r"<style", text, re.I)):
        failures.append("404 response is not pages/404.html (no title, stylesheet or noindex, or an inline <style>)")

    squeezed = compressed_paths()
    for path in squeezed:
        encoding = content_encoding(base + path)
        if encoding not in ("br", "gzip", "zstd", "deflate"):
            failures.append(f"{path}: not compressed (Content-Encoding {encoding!r}) though br and gzip were offered")

    if failures:
        print(f"Smoke test FAILED against {base} ({len(failures)} problem(s)):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"Smoke test passed against {base}: landing page, stylesheet, robots.txt, sitemap.xml")
    print(f"and its {len(paths)} URL(s), {len(found)} explorable(s), README paths, {len(hidden_sources)} source")
    print(f"path(s) not served, the 404 page and compression of {len(squeezed)} html, css, js and svg")
    print("file(s), all with every header from server/sws.toml and no X-Robots-Tag.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
