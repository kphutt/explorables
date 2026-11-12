#!/usr/bin/env python3
"""Check the built explorables before they can be deployed.

Explorables are standalone interactive pages served from explorables.kphutt.com, their own
origin, so kphutt.com keeps script-src 'none'. Here a page may load its own script files.
Everything else is held to the same rules as kphutt.com, applied by scripts/rules.py:

  - no inline code: no inline <script>, no <style> element, no style= or on...= attribute,
    no javascript: URL;
  - nothing loaded from another origin, by any page, stylesheet or script module;
  - every page can be found in search: no page but 404.html says noindex, by meta tag or
    X-Robots-Tag header, and each has a title, a description and its own canonical URL.
    404.html must say noindex;
  - robots.txt allows everything and names the sitemap, and sitemap.xml lists exactly the
    landing page and every explorable, by absolute URL on ORIGIN;
  - server/sws.toml sends the full header set, with a Content-Security-Policy no weaker
    than POLICY_FLOOR on any directive, Trusted Types with no policy allowed, COEP,
    X-Frame-Options, HSTS with includeSubDomains and without preload, compression, every
    server feature explorables do not use written out as off (rules.SERVER_FEATURES_OFF),
    idle-timeout of at least 1, and a long but not immutable cache for fonts and favicon.svg;
  - every pages/<slug>/ has an index.html and a README.md, and no README is in the
    output, where the server would serve it;
  - nothing for building is in the output either: no src/ folder of readable sources,
    no node_modules/, package.json, lockfile or source map;
  - no dot-files in the output;
  - the Dockerfile builds on one static-web-server image, pinned by version and digest.

Run it against the build directory:

    python scripts/build.py
    python scripts/check.py public
"""

from __future__ import annotations

import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rules  # noqa: E402
from build import ORIGIN, SOURCES, page_paths  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "pages"
CONFIG = REPO / "server" / "sws.toml"
DOCKERFILE = REPO / "Dockerfile"

# The weakest policy explorables may ship: each directive maps to the only sources it may
# hold, and a directive not listed may only be 'none'. So script-src gaining
# 'unsafe-inline', a hash, a nonce, another origin or a wildcard fails, and so does
# default-src 'self'.
POLICY_FLOOR = {
    "default-src": {"'none'"},
    "script-src": {"'self'"},
    "style-src": {"'self'"},
    "img-src": {"'self'"},
    "font-src": {"'self'"},
    "connect-src": {"'none'"},
    "object-src": {"'none'"},
    "base-uri": {"'none'"},
    "form-action": {"'none'"},
    "frame-ancestors": {"'none'"},
}
# Every directive in the floor must be written out, connect-src 'none' included, so the
# policy says in so many words that a page makes no network calls. The three restrict-only
# directives below are required too, and check_server checks their values:
# rules.policy_problems accepts any value for them.
REQUIRED_DIRECTIVES = (*POLICY_FLOOR, "require-trusted-types-for", "trusted-types", "upgrade-insecure-requests")
# The exact value each restrict-only directive must have. trusted-types 'none' means no
# script can create a Trusted Types policy, so nothing can turn a string into HTML or code.
RESTRICT_ONLY_VALUES = {
    "require-trusted-types-for": ["'script'"],
    "trusted-types": ["'none'"],
    "upgrade-insecure-requests": [],
}

REQUIRED_HEADERS = {
    "X-Content-Type-Options": {"nosniff"},
    "Referrer-Policy": {"no-referrer"},
    "Cross-Origin-Opener-Policy": {"same-origin"},
    "Cross-Origin-Resource-Policy": {"same-origin"},
    "Cross-Origin-Embedder-Policy": {"require-corp"},
    # frame-ancestors 'none' already forbids framing; this says the same to older browsers.
    "X-Frame-Options": {"DENY"},
}

# kphutt.com's Permissions-Policy, which this origin keeps equal. When that site's list
# changes, change this and server/sws.toml together.
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()"

# includeSubDomains is required here, and preload refused (server/sws.toml).
REFUSED_HSTS_FLAGS = ("preload",)

# Static files whose names carry no content hash: fonts and favicon.svg. They get a long
# cache, never immutable, and at least this long. LONG_CACHE_SOURCES are the rules that
# must give it to them.
MIN_LONG_CACHE = 2592000  # 30 days
LONG_CACHE_SOURCES = ("**/*.{woff2,woff}", "**/favicon.svg")

# The one page kept out of search: it answers for every missing path.
NOT_FOUND = "404.html"

# Files the output must have, and why.
EXPECTED_FILES = {
    "index.html": "the landing page would 404",
    "404.html": "missing pages would get the server's built-in page, whose inline <style> the CSP blocks",
    "robots.txt": "crawlers would not be pointed at the sitemap",
    "sitemap.xml": "search engines would have to find each explorable on their own",
}

# Build inputs that must never be served: readable sources, the npm toolchain and source
# maps. Folders by name, files by name or suffix.
TOOLING_DIRS = {SOURCES, "node_modules"}
TOOLING_FILES = {"package.json", "package-lock.json", "npm-shrinkwrap.json"}
TOOLING_SUFFIXES = (".map",)

# The server image: static-web-server, by version tag and digest, so a build can never pick
# up a different image under the same name.
BASE_IMAGE = re.compile(r"^ghcr\.io/static-web-server/static-web-server:[0-9][0-9A-Za-z.\-]*@sha256:[0-9a-f]{64}$")

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

SLUG = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")

ATTR = re.compile(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")


def attributes(tag: str) -> dict:
    return {m.group(1).lower(): next(v for v in m.groups()[1:] if v is not None) for m in ATTR.finditer(tag)}


def check_server(failures: list, config: Path = CONFIG) -> None:
    headers = rules.check_server_headers(failures, config, POLICY_FLOOR, REQUIRED_DIRECTIVES, REQUIRED_HEADERS,
                                         REFUSED_HSTS_FLAGS)
    name = config.relative_to(config.parent.parent).as_posix()
    if headers is None:
        return
    policy = rules.parse_policy(headers.get("content-security-policy") or "")
    for directive, want in RESTRICT_ONLY_VALUES.items():
        if directive in policy and [s.lower() for s in policy[directive]] != want:
            failures.append(f"{name}: Content-Security-Policy must have {' '.join([directive, *want])}, "
                            f"got {' '.join([directive, *policy[directive]])}")
    hsts = [t.strip().lower() for t in (headers.get("strict-transport-security") or "").split(";")]
    if "includesubdomains" not in hsts:
        failures.append(f"{name}: Strict-Transport-Security must have includeSubDomains")
    if headers.get("permissions-policy") != PERMISSIONS_POLICY:
        failures.append(f"{name}: Permissions-Policy must equal kphutt.com's, {PERMISSIONS_POLICY!r} (PERMISSIONS_POLICY in scripts/check.py)")
    if not headers.get("cache-control"):
        failures.append(f"{name}: no Cache-Control header on the catch-all rule")
    # On every response, so it would hide every page. 404.html says noindex for itself.
    if hides(headers.get("x-robots-tag") or ""):
        failures.append(f"{name}: X-Robots-Tag {headers['x-robots-tag']!r} would keep every page out of search")

    parsed = tomllib.loads(config.read_text(encoding="utf-8"))
    header_rules = (parsed.get("advanced") or {}).get("headers") or []
    for rule in header_rules:
        cache = {k.lower(): v for k, v in rule.get("headers", {}).items()}.get("cache-control", "")
        # Nothing here is named by its content's hash, so nothing may be cached as unchanging.
        if "immutable" in cache.lower():
            failures.append(f"{name}: rule for {rule.get('source')!r} is immutable, but no name here carries a content hash")
    for source in LONG_CACHE_SOURCES:
        match = [r for r in header_rules if r.get("source") == source]
        cache = {k.lower(): v for k, v in (match[0].get("headers", {}) if match else {}).items()}.get("cache-control", "")
        age = re.search(r"max-age=(\d+)", cache)
        if not age or int(age.group(1)) < MIN_LONG_CACHE:
            failures.append(f"{name}: no rule for {source!r} with Cache-Control max-age of at least {MIN_LONG_CACHE}")

    # Every server feature explorables do not use is off, idle-timeout (the
    # GHSA-2fch-9x9r-mxmv fix) is at least 1, and no [advanced] table but headers exists.
    rules.check_server_settings(failures, config, frozenset({"headers"}))
    general = parsed.get("general", {})
    for key, want in (("page404", "404.html"), ("include-hidden", False), ("compression", True)):
        if general.get(key) != want:
            failures.append(f"{name}: {key} must be {want!r}, got {general.get(key)!r}")


def hides(directives: str) -> bool:
    """True if a robots meta content or X-Robots-Tag value keeps a page out of search."""
    return bool({t.strip().lower() for t in directives.split(",")} & {"noindex", "none"})


def page_url(page: str) -> str:
    """The canonical URL of a built page, from its path in the output."""
    return f"{ORIGIN}/{page[:-len('index.html')] if page.endswith('index.html') else page}"


def check_pages(root: Path, failures: list) -> None:
    rules.check_inline_code(root, failures)
    rules.check_no_outside_loads(root, ORIGIN, failures)

    for path in sorted(root.rglob("*.html")):
        html = path.read_text(encoding="utf-8", errors="replace")
        page = path.relative_to(root).as_posix()

        metas = [attributes(t) for t in re.findall(r"<meta\b[^>]*>", html, re.I)]
        # robots, and any one crawler by name (googlebot, bingbot).
        robots = [a for a in metas if a.get("name", "").lower() == "robots" or a.get("name", "").lower().endswith("bot")]
        says_noindex = any(hides(a.get("content", "")) for a in robots)
        if page == NOT_FOUND:
            if not says_noindex:
                failures.append(f'{page}: no <meta name="robots" content="noindex"> -- an error page should not be indexed')
        else:
            if says_noindex:
                failures.append(f"{page}: a robots meta tag says noindex, which keeps the page out of search")
            title = re.search(r"<title\b[^>]*>(.*?)</title\s*>", html, re.S | re.I)
            if not title or not title.group(1).strip():
                failures.append(f"{page}: no <title>, or an empty one")
            descriptions = [a.get("content", "") for a in metas if a.get("name", "").lower() == "description"]
            if len(descriptions) != 1 or not descriptions[0].strip():
                failures.append(f'{page}: needs exactly one non-empty <meta name="description">')
            links = [attributes(t) for t in re.findall(r"<link\b[^>]*>", html, re.I)]
            canonical = [a.get("href") for a in links if "canonical" in a.get("rel", "").lower().split()]
            if canonical != [page_url(page)]:
                failures.append(f"{page}: canonical link is {canonical}, expected [{page_url(page)!r}]")

        # A <script> the closing-tag pattern in check_inline_code cannot see would swallow
        # the rest of the page, and whatever it holds would be missed.
        if len(re.findall(r"<script\b", html, re.I)) != len(re.findall(r"<script\b[^>]*>.*?</script\s*>", html, re.S | re.I)):
            failures.append(f"{page}: a <script> without its </script>")
        for tag in re.findall(r"<script\b[^>]*>", html, re.I):
            src = attributes(tag).get("src")
            if src is not None:
                check_same_origin(page, src, failures)

        for ref in re.findall(r'(?:href|src)=["\']?([^"\'>\s]+)', html):
            target = rules.resolve_ref(ref, ORIGIN, root, path)
            if target is not None and not target.exists():
                failures.append(f"{page}: broken internal reference {ref}")

    # Script modules can load other modules. Each specifier must stay on this origin.
    imports = re.compile(
        r"""(?:\bimport\s*\(\s*|\bimport\s+(?:[^'";]*?\s+from\s+)?|\bexport\s+[^'";]*?\s+from\s+)["']([^"']+)["']"""
    )
    for path in sorted([*root.rglob("*.js"), *root.rglob("*.mjs")]):
        page = path.relative_to(root).as_posix()
        for spec in imports.findall(path.read_text(encoding="utf-8", errors="replace")):
            check_same_origin(page, spec, failures)


def check_same_origin(page: str, url: str, failures: list) -> None:
    url = url.strip()
    if url.startswith("//") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url):
        failures.append(f"{page}: loads script {url} from another origin, or by absolute URL -- use a relative one")


def check_discovery(root: Path, failures: list) -> None:
    """robots.txt names the sitemap and blocks nothing; the sitemap lists exactly the pages."""
    robots = root / "robots.txt"
    if robots.is_file():
        lines = [line.split("#", 1)[0].strip() for line in robots.read_text(encoding="utf-8").splitlines()]
        if f"Sitemap: {ORIGIN}/sitemap.xml" not in lines:
            failures.append(f"robots.txt: no 'Sitemap: {ORIGIN}/sitemap.xml' line")
        blocked = [line for line in lines if line.lower().startswith("disallow:") and line.split(":", 1)[1].strip()]
        if blocked:
            failures.append(f"robots.txt: {', '.join(blocked)} keeps pages out of search")
    sitemap = root / "sitemap.xml"
    if not sitemap.is_file():
        return
    try:
        locs = [(e.text or "").strip() for e in ET.parse(sitemap).getroot().iter(f"{SITEMAP_NS}loc")]
    except ET.ParseError as e:
        failures.append(f"sitemap.xml is not valid XML: {e}")
        return
    paths = []
    for loc in locs:
        if not loc.startswith(ORIGIN + "/"):
            failures.append(f"sitemap.xml lists {loc!r}, which is not an absolute URL on {ORIGIN}")
            continue
        path = loc[len(ORIGIN):]
        paths.append(path)
        if not path.endswith("/") or not (root / path.strip("/") / "index.html").is_file():
            failures.append(f"sitemap.xml lists {loc}, which is not a page in the build")
    if len(paths) != len(set(paths)):
        failures.append("sitemap.xml lists a URL twice")
    for path in page_paths(root):
        if path not in paths:
            failures.append(f"sitemap.xml does not list {ORIGIN}{path}")


def check_layout(source: Path, root: Path, failures: list) -> None:
    for name, why in EXPECTED_FILES.items():
        if not (root / name).is_file():
            failures.append(f"{name} missing from the output -- {why}")
    if source.is_dir():
        for folder in sorted(p for p in source.iterdir() if p.is_dir()):
            where = f"pages/{folder.name}/"
            if not SLUG.match(folder.name):
                failures.append(f"{where}: not a slug (lowercase letters, digits and hyphens)")
            if not (folder / "README.md").is_file():
                failures.append(f"{where}: no README.md saying what the page is and where its parts came from")
            if not (folder / "index.html").is_file():
                failures.append(f"{where}: no index.html")
            if (folder / SOURCES).exists() and not (folder / SOURCES).is_dir():
                failures.append(f"{where}{SOURCES}: not a folder -- the name is kept for readable sources")
    else:
        failures.append(f"{source} not found")
    served = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.name.lower().startswith("readme"))
    if served:
        failures.append(f"a README is in the output, where the server would serve it: {', '.join(served)}")
    tooling = sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*")
        if (p.is_dir() and p.name in TOOLING_DIRS)
        or (p.is_file() and (p.name in TOOLING_FILES or p.name.endswith(TOOLING_SUFFIXES)))
    )
    if tooling:
        failures.append(f"build sources or tooling in the output, where the server would serve them: {', '.join(tooling)}")
    hidden = rules.hidden_files(root)
    if hidden:
        failures.append(f"hidden files in the output: {', '.join(sorted(hidden))}")


def check_base_image(failures: list, dockerfile: Path = DOCKERFILE) -> None:
    froms = re.findall(r"^FROM\s+(\S+)", dockerfile.read_text(encoding="utf-8"), re.M | re.I)
    if len(froms) != 1 or not BASE_IMAGE.match(froms[0]):
        failures.append(
            f"{dockerfile.name}: must build FROM one static-web-server image pinned by version and "
            f"digest (ghcr.io/static-web-server/static-web-server:X.Y.Z@sha256:...), got {froms}"
        )


def check(root: Path, source: Path = SOURCE, config: Path = CONFIG, dockerfile: Path = DOCKERFILE) -> list:
    failures = []
    check_layout(source, root, failures)
    check_pages(root, failures)
    check_discovery(root, failures)
    check_server(failures, config)
    check_base_image(failures, dockerfile)
    return failures


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "public")
    if not root.is_dir():
        sys.exit(f"FAIL: build directory not found: {root} (run scripts/build.py)")
    failures = check(root)
    if failures:
        print(f"Explorables check FAILED ({len(failures)} problem(s)):")
        for f in failures:
            print(f"  - {f}")
        return 1
    slugs = [p.name for p in SOURCE.iterdir() if p.is_dir()]
    print(f"Explorables check passed: {len(slugs)} explorable(s), all in the sitemap and findable")
    print("in search (only 404.html noindex), each with a title, description and canonical URL,")
    print("no inline code, nothing loaded from another origin, no README, source, tooling or")
    print("dot-file served, CSP at or above the floor in server/sws.toml, connect-src 'none',")
    print("every required header set, base image pinned by version and digest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
