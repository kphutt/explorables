#!/usr/bin/env python3
"""Tell IndexNow search engines which pages a deploy changed.

IndexNow (https://www.indexnow.org/documentation) is a single POST that tells Bing, Yandex,
Naver, Seznam and the other participating engines that URLs have changed, so they recrawl
them instead of waiting to notice. Google does not take part; it reads the sitemap.

The deploy job runs it in two steps around the promotion, as kphutt.com's deploy does:

    python3 scripts/indexnow.py snapshot BEFORE.xml   # the live sitemap, before promoting
    python3 scripts/indexnow.py submit BEFORE.xml     # after: submit what changed

Only pages that are new, or whose <lastmod> changed, are submitted, because the protocol asks
for changed URLs rather than the whole site on every deploy. The key proves the request comes
from the site's owner: pages/indexnow.txt holds it, and the engines fetch that file from the
site to check it. It is public by design, so it is not a secret, and it is this host's own,
not kphutt.com's.

A failure here never fails a deploy: both workflow steps are continue-on-error. Standard
library only.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import ORIGIN  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
KEY_FILE = REPO / "pages" / "indexnow.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

# What IndexNow accepts as a key: 8 to 128 of a-z, A-Z, 0-9 and dashes.
KEY = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def entries(sitemap: bytes) -> dict:
    """URL -> lastmod (or "") for every <url> in a sitemap. Empty for an unreadable one."""
    try:
        root = ET.fromstring(sitemap)
    except ET.ParseError:
        return {}
    found = {}
    for url in root.iter(f"{NS}url"):
        loc = (url.findtext(f"{NS}loc") or "").strip()
        if loc:
            found[loc] = (url.findtext(f"{NS}lastmod") or "").strip()
    return found


def changed(before: bytes, after: bytes, origin: str) -> list:
    """URLs on origin in the new sitemap that are new or whose lastmod changed."""
    old = entries(before)
    return sorted(loc for loc, mod in entries(after).items()
                  if loc.startswith(origin + "/") and old.get(loc) != mod)


def payload(urls: list, origin: str, key: str) -> dict:
    return {
        "host": urlsplit(origin).hostname,
        "key": key,
        "keyLocation": f"{origin}/{KEY_FILE.name}",
        "urlList": urls,
    }


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def main(argv: list) -> int:
    if len(argv) != 3 or argv[1] not in ("snapshot", "submit"):
        sys.exit("usage: indexnow.py snapshot|submit BEFORE.xml")
    before = Path(argv[2])
    if argv[1] == "snapshot":
        try:
            before.write_bytes(fetch(f"{ORIGIN}/sitemap.xml"))
        except OSError as e:
            print(f"could not read the live sitemap ({e}); every page will count as changed")
            before.write_bytes(b"")
        return 0
    old = before.read_bytes() if before.is_file() else b""
    urls = changed(old, fetch(f"{ORIGIN}/sitemap.xml"), ORIGIN)
    if not urls:
        print("IndexNow: no page changed, nothing submitted")
        return 0
    body = json.dumps(payload(urls, ORIGIN, KEY_FILE.read_text(encoding="utf-8").strip())).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"IndexNow: submitted {len(urls)} URL(s), HTTP {r.status}")
        for u in urls:
            print(f"  {u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
