"""The page and header rules the gate (scripts/check.py) applies.

Explorables were first served from kphutt.com's repository, and these checks were shared
with that site's own gate there. They are copied here so this repository stands alone. The
rules are unchanged; only the site's defaults are gone.

  - parse_policy and policy_problems read a Content-Security-Policy the way a browser does,
    and list every way it is weaker than a floor;
  - check_inline_code fails any inline code a policy would have to allow;
  - check_no_outside_loads fails anything a page loads from another origin;
  - check_server_headers reads the server config and checks its full header set;
  - check_server_settings checks that every server feature explorables do not use is off;
  - resolve_ref and hidden_files are helpers for the broken-link and dot-file checks.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

# One year. HSTS shorter than this protects little and is what scanners flag.
MIN_HSTS_MAX_AGE = 31536000

# Directives that only ever restrict, so policy_problems accepts any value for them (the
# gate checks their exact values itself). Every other directive not in the floor may only be
# 'none': an unlisted fetch directive such as script-src-elem or media-src at 'self' would
# loosen the default-src 'none' fallback. report-uri and report-to are deliberately not
# here: they send violation reports to a URL, which is a request to wherever the policy
# names. They fall under the 'none'-only rule like any other unlisted directive, so adding a
# reporting endpoint is a decision, not a drive-by.
RESTRICT_ONLY = {"sandbox", "upgrade-insecure-requests", "require-trusted-types-for", "trusted-types"}


def parse_policy(policy: str) -> dict:
    """Split a CSP string into {directive: [sources]} the way a browser does.

    Browsers split on ASCII whitespace only, lowercase directive names, and keep the
    first of a repeated directive. Python's str.split() would also split on a no-break
    space, so a policy a browser reads as one unknown directive would look valid here;
    hence the explicit separator.
    """
    parsed = {}
    for part in policy.split(";"):
        tokens = [tok for tok in re.split(r"[\t\n\f\r ]+", part) if tok]
        if tokens:
            parsed.setdefault(tokens[0].lower(), tokens[1:])
    return parsed


def policy_problems(policy: str, required: tuple, floor: dict) -> list:
    """Every way `policy` is weaker than `floor`. An empty list means it holds.

    `floor` maps each directive to the only sources it may hold. A directive not listed may
    only be 'none'. So 'unsafe-inline', a hash, a nonce, another origin, a wildcard, a
    scheme like https: or data:, or default-src 'self' all fail.
    """
    problems = []
    if not policy.isascii() or any(ord(c) < 32 and c not in "\t\n\f\r" for c in policy):
        problems.append("contains non-ASCII or control characters, which browsers do not treat as separators")
    parsed = parse_policy(policy)
    for name in required:
        if name not in parsed:
            problems.append(f"{name} is missing")
    for name, sources in parsed.items():
        if name in RESTRICT_ONLY:
            continue
        allowed = floor.get(name, {"'none'"})
        extra = [s for s in sources if s.lower() not in allowed]
        if extra:
            problems.append(f"{name} allows {' '.join(extra)} (the floor is {' '.join(sorted(allowed))})")
        if not sources:
            problems.append(f"{name} has no value")
    return problems


# A JSON-LD block is data and never runs. Recognised by its exact type attribute, not by
# the text "ld+json" appearing anywhere among the attributes.
JSON_LD = re.compile(r"""(?:^|\s)type\s*=\s*["']?application/ld\+json["']?(?:\s|$)""", re.I)

# A src attribute on its own, not data-src or similar.
SRC_ATTR = re.compile(r"""(?:^|\s)src\s*=""", re.I)

# Any type attribute. A browser reads only the first of two, so a second one could hide a
# script typed as JavaScript behind a JSON-LD type later in the tag. An attribute can
# follow whitespace, a quote or a slash.
TYPE_ATTR = re.compile(r"""(?:^|[\s"'/])type\s*=""", re.I)


def json_ld_problem(attrs: str, body: str):
    """Why a <script type="application/ld+json"> block is not plain data, or None.

    A data block is never run, so the policy has nothing to allow for it. That only holds
    for exactly what search engines read: one type attribute, no src, and a body that is a
    JSON object or array. "<!--" and "<script" inside a script element change where the
    browser ends it, so neither may appear.
    """
    if len(TYPE_ATTR.findall(attrs)) != 1:
        return "has more than one type attribute"
    if SRC_ATTR.search(attrs):
        return "has a src attribute"
    if "<!--" in body or re.search(r"<script", body, re.I):
        return 'contains "<!--" or "<script", which changes where the element ends'
    try:
        data = json.loads(body)
    except ValueError as e:
        return f"is not valid JSON ({e})"
    if not isinstance(data, (dict, list)):
        return "is not a JSON object or array"
    return None


def check_inline_code(root: Path, failures: list) -> None:
    """The built pages must contain no code the policy would have to allow.

    The policy is script-src 'self' with no 'unsafe-inline' and no hashes, which only holds
    if the pages contain nothing that needs them. So look for every form of inline code:
    inline scripts, <style> elements, style= attributes, event-handler attributes and
    javascript: URLs. A <script src=...> with nothing between its tags is allowed; where it
    points is check.py's to check. JSON-LD is data, not executed, so it stays, as long as
    it is only data (json_ld_problem).
    """
    # SVG files are documents too: opened directly, one can carry script or handlers.
    for path in sorted([*root.rglob("*.html"), *root.rglob("*.svg")]):
        html = path.read_text(encoding="utf-8", errors="replace")
        page = path.relative_to(root).as_posix()

        for attrs, body in re.findall(r"<script\b([^>]*)>(.*?)</script\s*>", html, re.S | re.I):
            if JSON_LD.search(attrs):
                problem = json_ld_problem(attrs, body)
                if problem:
                    failures.append(f"{page}: JSON-LD block {problem}")
                continue
            if SRC_ATTR.search(attrs) and not body.strip():
                continue
            # With both src= and a body, the browser runs the file and ignores the body, so
            # the body could only mislead a reader. Refused like inline code.
            kind = "external script with a body" if SRC_ATTR.search(attrs) else "inline script"
            snippet = " ".join((attrs + " " + body).split())[:60]
            failures.append(f"{page}: {kind}, which script-src 'self' blocks (starts: {snippet})")
        if re.search(r"<style[\s>]", html, re.I):
            failures.append(f"{page}: inline <style> element -- move the CSS into a stylesheet file")
        # An attribute can follow whitespace, a slash or a closing quote (<svg/onload=,
        # <div class="a"style=), and may have spaces around its =.
        if re.search(r"""<[^>]+[\s/"']style\s*=""", html, re.I):
            failures.append(f"{page}: inline style= attribute -- move it into a stylesheet file")
        handler = re.search(r"""<[^>]+[\s/"'](on[a-z]+)\s*=""", html, re.I)
        if handler:
            failures.append(f"{page}: event-handler attribute {handler.group(1)}= is inline script")
        if re.search(r"""(?:href|src|action|formaction|data)\s*=\s*["']?\s*javascript:""", html, re.I):
            failures.append(f"{page}: javascript: URL is inline script")


def check_no_outside_loads(root: Path, base: str, failures: list) -> None:
    """Nothing the browser fetches by itself may come from another origin.

    Outbound <a> links are fine -- the visitor clicks them, the page does not load them.
    Stylesheets, icons, preloads, images, fonts and CSS url()s are what the page loads, and
    the policy only allows this origin for those. Catch it here rather than as a silent
    console error on the live site. @font-face is allowed (the policy has font-src 'self'),
    and its url() is held to the same rule. @import is not: link each stylesheet instead.
    """
    loads = []
    for path in sorted(root.rglob("*.html")):
        html = path.read_text(encoding="utf-8", errors="replace")
        page = path.relative_to(root).as_posix()
        for tag in re.findall(r"<link\b[^>]*>", html, re.I):
            rel = re.search(r"""rel=["']?([^"'>]+?)["']?(?:\s|>|/)""", tag, re.I)
            rel = rel.group(1).lower() if rel else ""
            # alternate/canonical/etc are metadata, not loads.
            if not any(r in rel.split() for r in ("stylesheet", "icon", "apple-touch-icon", "mask-icon", "preload", "prefetch", "manifest", "modulepreload")):
                continue
            href = re.search(r"""href=["']?([^"'>\s]+)""", tag, re.I)
            if href:
                loads.append((page, href.group(1)))
        for src in re.findall(r"""<(?:img|source|iframe|embed|video|audio|track|input)\b[^>]*\ssrc\s*=\s*["']?([^"'>\s]+)""", html, re.I):
            loads.append((page, src))
        for url in re.findall(r"""<video\b[^>]*\sposter\s*=\s*["']?([^"'>\s]+)""", html, re.I):
            loads.append((page, url))
        for url in re.findall(r"""<object\b[^>]*\sdata\s*=\s*["']?([^"'>\s]+)""", html, re.I):
            loads.append((page, url))
        # srcset holds a comma-separated list of "URL width" candidates.
        for srcset in re.findall(r"""\ssrcset\s*=\s*["']([^"']+)["']""", html, re.I):
            for candidate in srcset.split(","):
                if candidate.strip():
                    loads.append((page, candidate.split()[0]))
    for path in sorted(root.rglob("*.css")):
        css = path.read_text(encoding="utf-8", errors="replace")
        page = path.relative_to(root).as_posix()
        if re.search(r"@import", css, re.I):
            failures.append(f"{page}: @import -- link each stylesheet from the page instead")
        for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", css, re.I):
            loads.append((page, url))
    for page, url in loads:
        if url.startswith("data:"):
            failures.append(f"{page}: data: URL load {url[:40]} -- the policy does not allow data:")
        elif url.startswith("//") or (re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url) and not url.startswith(base + "/")):
            failures.append(f"{page}: loads {url} from another origin")
        elif url.startswith(base + "/"):
            # Same origin, but pinned to its production host name. On any other host (a
            # deploy candidate's own URL) that is another origin, so the policy blocks it
            # there. Canonical links are metadata and stay absolute.
            failures.append(f"{page}: loads {url} by absolute URL -- use a relative one")


def check_server_headers(
    failures: list,
    config_path: Path,
    floor: dict,
    required_directives: tuple,
    required_headers: dict,
    refused_hsts_flags: tuple,
):
    """The server config must send the full header set, with a policy at or above the floor.

    This is the policy every response is served with, the 404 page included. Loosening it
    below the floor fails the build. Returns the catch-all rule's headers, lowercased, so a
    caller can check more of them, or None if there is no catch-all rule to read.
    """
    name = config_path.relative_to(config_path.parent.parent).as_posix()
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        failures.append(f"{name} could not be read: {e}")
        return None

    general = config.get("general", {})
    # The server's built-in versions of these would add HSTS with includeSubDomains and
    # preload, and a one-year cache on files whose names never change.
    for switch in ("security-headers", "cache-control-headers"):
        if general.get(switch) is not False:
            failures.append(f"{name}: {switch} must be false -- the explicit headers replace it")

    rules = (config.get("advanced") or {}).get("headers") or []
    catch_all = [r for r in rules if r.get("source") == "**"]
    if not catch_all:
        failures.append(f"{name}: no catch-all [[advanced.headers]] rule with source = \"**\"")
        return None

    # HTTP header names are case-insensitive but TOML keys are not, so a second,
    # differently-cased copy of a header could slip a weaker value past these checks.
    # Compare lowercased, and refuse duplicates outright.
    def lowered(rule):
        out = {}
        for key, value in rule.get("headers", {}).items():
            if key.lower() in out:
                failures.append(f"{name}: rule for {rule.get('source')!r} sets {key} twice (names differ only in case)")
            out[key.lower()] = value
        return out

    headers = lowered(catch_all[0])

    # A later rule replaces an earlier value, so only Cache-Control and Content-Type may be
    # set by the narrower rules. Anything else there could silently weaken the catch-all.
    for rule in rules:
        if rule is catch_all[0]:
            continue
        for header in lowered(rule):
            if header not in ("cache-control", "content-type"):
                failures.append(
                    f"{name}: rule for {rule.get('source')!r} sets {header}, which would "
                    f"override the catch-all for those files"
                )

    policy = headers.get("content-security-policy")
    if not policy:
        failures.append(f"{name}: no Content-Security-Policy header")
    else:
        for problem in policy_problems(policy, required_directives, floor):
            failures.append(f"{name}: Content-Security-Policy is weaker than the floor: {problem}")

    hsts = headers.get("strict-transport-security", "")
    max_age = re.search(r"max-age=(\d+)", hsts)
    if not max_age or int(max_age.group(1)) < MIN_HSTS_MAX_AGE:
        failures.append(f"{name}: Strict-Transport-Security max-age must be at least {MIN_HSTS_MAX_AGE}")
    # Hard to undo, and covers names served elsewhere. Adding one is a decision for the
    # owner, so it fails here until this check is changed deliberately alongside it.
    for flag in refused_hsts_flags:
        if flag in hsts.lower():
            failures.append(f"{name}: Strict-Transport-Security has {flag}, which needs an explicit decision")

    for header, allowed in required_headers.items():
        if headers.get(header.lower()) not in allowed:
            failures.append(f"{name}: {header} is {headers.get(header.lower())!r}, expected one of {sorted(allowed)}")
    if not headers.get("permissions-policy"):
        failures.append(f"{name}: no Permissions-Policy header")
    return headers


# Server features explorables do not use, and the value that turns each off. Each one reads
# the request, so off is less code an attacker's request can reach. Each must be written out,
# not left to the default: a value in the config file overrides the binary's default and any
# SERVER_* environment variable, so nothing outside the file can turn one back on.
SERVER_FEATURES_OFF = {
    "health": False,
    "metrics": False,
    "maintenance-mode": False,
    "accept-markdown": False,
    "cors-allow-origins": "",
    "basic-auth": "",
    "page-fallback": "",
    "directory-listing": False,
    "directory-listing-download": [],
    "compression-static": False,
    "follow-symlinks": False,
    "tls": False,
    "http2": False,
    "https-redirect": False,
    "use-relative-root": False,
    "etag": False,
    "log-remote-address": False,
    "log-x-real-ip": False,
    "log-forwarded-for": False,
}

# Every other [general] key a config may hold. A key in neither list fails: v3 ignores a
# key it does not know with only a warning, so a misspelled one would silently leave its
# feature at the default, and a new key is a new feature, which is a decision.
SERVER_KEYS_ALLOWED = {
    "host", "port", "root", "log-level", "page404", "security-headers", "cache-control-headers",
    "compression", "include-hidden", "redirect-trailing-slash", "index-files", "idle-timeout",
    "text-charset",
}


def server_settings_problems(name: str, config: dict, advanced_allowed: frozenset) -> list:
    """What in a parsed server config turns on a feature explorables do not use.

    advanced_allowed is the set of [advanced] tables the config may have. The rest
    (rewrites, redirects, virtual-hosts, memory-cache) must be absent, which is the only way
    to turn them off.
    """
    problems = []
    for section in config:
        if section not in ("general", "advanced"):
            problems.append(f"{name}: [{section}] is not a section this gate knows")
    general = config.get("general") or {}
    for key, off in SERVER_FEATURES_OFF.items():
        if key not in general:
            problems.append(f"{name}: {key} must be set to {off!r}, not left to the default")
        elif general[key] != off or type(general[key]) is not type(off):
            problems.append(f"{name}: {key} is {general[key]!r}, but must be {off!r}: the site does not use it")
    for key in general:
        if key not in SERVER_FEATURES_OFF and key not in SERVER_KEYS_ALLOWED:
            problems.append(f"{name}: {key} is not a key this gate knows (misspelled, or a feature to decide on)")
    # Closes a connection that sends or reads nothing for this long (GHSA-2fch-9x9r-mxmv).
    # 0 turns it off, and leaving it out trusts the default.
    timeout = general.get("idle-timeout")
    if type(timeout) is not int or timeout < 1:
        problems.append(f"{name}: idle-timeout must be set to a whole number of seconds, at least 1, got {timeout!r}")
    for table in config.get("advanced") or {}:
        if table not in advanced_allowed:
            problems.append(f"{name}: [advanced.{table}] turns on a feature the site does not use")
    return problems


def check_server_settings(failures: list, config_path: Path,
                          advanced_allowed: frozenset = frozenset({"headers"})) -> None:
    """Every server feature explorables do not use is written out as off."""
    name = config_path.relative_to(config_path.parent.parent).as_posix()
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        failures.append(f"{name} could not be read: {e}")
        return
    failures.extend(server_settings_problems(name, config, advanced_allowed))


def resolve_ref(ref: str, base: str, root: Path, page: Path):
    """Map a reference in the built HTML to the file it should resolve to.

    Returns None for anything not checkable here: other sites and mailto/data/anchors.
    External links are deliberately out of scope -- they break for reasons outside this
    repository and would make the build fail on someone else's outage.
    """
    ref = ref.split("#", 1)[0].split("?", 1)[0].strip()
    if not ref:
        return None
    if ref.startswith(("mailto:", "data:", "javascript:", "tel:", "//")):
        return None

    if ref.startswith(base):
        ref = ref[len(base):] or "/"
    elif re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", ref):
        return None  # some other origin

    if ref.startswith("/"):
        target = root / ref.lstrip("/")
    else:
        target = page.parent / ref

    # A directory URL is served by its index.html.
    if ref.endswith("/") or (target.is_dir()):
        target = target / "index.html"
    return target


def hidden_files(root: Path) -> list:
    """Every dot-file or dot-folder under root, or inside one."""
    return [
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if any(part.startswith(".") for part in p.relative_to(root).parts)
    ]
