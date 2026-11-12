# Explorables

Interactive pages that go with posts on [kphutt.com](https://kphutt.com/). Each one is a
standalone page: its own HTML, script, styles, images and fonts, with nothing running on a
server. They are served at `https://explorables.kphutt.com/<slug>/`.

## How it works

`pages/` holds the landing page, the 404 page and one folder per explorable.
`scripts/build.py` copies it to `public/`, leaving out every `README.md` and every `src/`
folder, and generates `robots.txt` and `sitemap.xml`. `scripts/check.py` then checks that
output against the rules below. The `Dockerfile` puts the checked output behind
[static-web-server](https://static-web-server.net), with the headers in `server/sws.toml`.

On every pull request, GitHub Actions runs the gate, builds the container and smoke-tests it.
On a merge to `main` it deploys to Cloud Run, blue-green: the new revision starts with no
traffic, is smoke-tested at its own URL, and only then gets all of it. If the smoke test fails,
the old revision keeps serving. `AGENTS.md` has the details.

```bash
python scripts/build.py && python scripts/check.py public   # build and check
python -m unittest discover -s scripts -p "test_*.py"       # the gate's own tests
python scripts/local_verify.py                              # all of the CI gate, locally
```

## Adding an explorable

1. Make a folder `pages/<slug>/`, with a slug of lowercase letters, digits and hyphens. It is
   the page's address: `https://explorables.kphutt.com/<slug>/`.
2. Put in it an `index.html`, its own script, style, image and font files, and a `README.md`
   that says what the page is and where its parts came from (a font's license, for one).
3. Run `python scripts/local_verify.py`. It fails if any of the rules below breaks.

The rules:

- Every page can be found in search: no `noindex`. Only `404.html` has one.
- Every page has a `<title>`, a `<meta name="description">` and a `<link rel="canonical">` to
  its own absolute URL, such as `https://explorables.kphutt.com/<slug>/`.
- Scripts and styles are files, loaded with `<script src>` and `<link rel="stylesheet">`. No
  inline `<script>` or `<style>`, no `style=` or `on...=` attributes, no `javascript:` URLs.
- Everything a page loads comes from this origin, by a relative URL. That includes fonts:
  bundle them, with their license.
- No network calls. The policy has `connect-src 'none'`, so `fetch` and the like are blocked.
- Trusted Types are required, and no policy may be created. Build the page with DOM methods
  (`textContent`, `createElement`) rather than by assigning strings to `innerHTML`. Set styles
  through the CSSOM (`element.style`), never a `style=` attribute.
- No dot-files. READMEs and `src/` folders stay in the repository and are never served.

## Security model

Each explorable runs its own JavaScript, so the pages live on their own origin. A browser
keeps `explorables.kphutt.com` and `kphutt.com` apart, so nothing a page here does can reach
the main site, and the main site keeps a policy with no script at all.

Every response, the 404 page included, carries a strict Content-Security-Policy: scripts,
styles, images and fonts from this origin only, no inline code, no network calls, and
Trusted Types with no policy allowed. It also sets HSTS, `X-Frame-Options: DENY`,
cross-origin isolation (COOP, COEP and CORP), `Referrer-Policy: no-referrer` and a
Permissions-Policy that turns off the camera, microphone, location and the rest. The policy
is written once, in `server/sws.toml`. `scripts/check.py` fails the build if any of it gets
weaker, and `scripts/smoke.py` checks that a running server sends exactly those headers.

Deploys are keyless. GitHub's OIDC token is exchanged for a short-lived Google identity that
can deploy this one Cloud Run service and nothing else, and only from `main`. No service
account key exists.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Licenses

- **Code** is under the Apache License 2.0 ([LICENSE](LICENSE)): the scripts, the server
  configuration, the workflows, and each page's markup, script and styles.
- **Content** is under Creative Commons Attribution 4.0 International
  ([LICENSE-CONTENT](LICENSE-CONTENT)): the words, numbers and data each explorable presents,
  including the text in its HTML and its README, and its images and screenshots. To reuse it,
  credit kphutt and link to <https://explorables.kphutt.com/>.
- **Fonts** keep their own licenses, which sit beside them in the explorable's folder.
- Pages link to the sources they cite. Those sources belong to their owners, and nothing here
  is affiliated with any company a page names.
