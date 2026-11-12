# Explorables

Interactive pages that go with posts on [kphutt.com](https://kphutt.com/). Each one is a
standalone static page, served at `https://explorables.kphutt.com/<slug>/`.

| Explorable | What it is |
|---|---|
| [backup-power](https://explorables.kphutt.com/backup-power/) | Five houses ride out the same two-week winter power outage, each with a different backup. |

## How it works

`pages/` holds the landing page, the 404 page and one folder per explorable. Its `assets/`
folder holds the fonts, icon and card previews the pages share. Pages are served as written,
without a minifier or npm.

The build script copies the pages to `public/`, leaving out the READMEs. It also generates
the robots file, the sitemap and an llms.txt, which welcome every crawler and list the
explorables. `scripts/check.py` checks that output against the rules below. The `Dockerfile`
serves the checked output with [static-web-server](https://static-web-server.net).

Each pull request runs the checks and smoke-tests the container. A merge to `main` deploys to
Cloud Run, blue-green. The new revision is smoke-tested at its own URL before it gets any
visitors, so a failed test leaves the old one serving. [AGENTS.md](AGENTS.md) has the details.

```bash
python scripts/build.py && python scripts/check.py public   # build and check
python scripts/local_verify.py                              # build, checks and unit tests
```

## Adding an explorable

1. Make a folder `pages/<slug>/`. The slug is lowercase letters, digits and hyphens, and it
   becomes the page's address. The name `assets` is taken.
2. Put the page's `index.html`, scripts, styles and images in it. Add a README that says what
   the page is and where its parts came from.
3. Use the shared fonts, or add a font to `pages/assets/fonts/` with its license.
4. Add a card to the landing page, `pages/index.html`, with a preview image, a title linking
   to the page, and one line saying what it is. The image goes in `pages/assets/previews/`.
5. Run `python scripts/local_verify.py`. It catches markup that breaks a rule.
6. Run the container, as [AGENTS.md](AGENTS.md) shows, and use the page through it with the
   browser console open. The server's headers make the browser block anything the check
   script misses.

The rules:

| Rule | What it means |
|---|---|
| Findable | A `<title>`, a `<meta name="description">`, a canonical link to the page's own absolute URL, and an icon link. Only `404.html` has a `noindex` meta tag. |
| No inline code | Scripts and styles are files. No inline `<script>` except a JSON-LD data block, and no `<style>`, `style=`, `on...=` or `javascript:` URL. |
| One origin | Everything a page loads comes from this site by a relative URL, fonts included. |
| No network calls | Scripts fetch nothing. The policy allows this site's `robots.txt` alone, because Lighthouse fetches it from inside the page. |
| No HTML strings | Trusted Types block handing a string to `innerHTML`. Build the DOM with `createElement` and `textContent`, and set styles through `element.style`. |
| No build tooling | No dot-files, and no `src/` folder, `node_modules/`, `package.json`, npm lockfile or source map in the output. |

## Security model

Explorables run their own JavaScript, so they live on a separate origin,
`explorables.kphutt.com`. A browser keeps that apart from kphutt.com, so the main site can
keep a policy that allows no script.

Every response, the 404 page included, carries a Content-Security-Policy. It blocks inline
code, loads from other origins and every network call but the robots.txt fetch. Each response
also sends HSTS, cross-origin isolation and a ban on framing. Referrers are not sent, and the camera, microphone and location
are off. The headers live in `server/sws.toml`. The checks fail if any of them weakens, and the
smoke test checks that a running server sends them.

Deploys are keyless. GitHub's OIDC token becomes a short-lived Google identity. It can push
only this site's images and deploy only its Cloud Run service, and only from `main`.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Licenses

- Code is under the Apache License 2.0 ([LICENSE](LICENSE)): the scripts, the server
  configuration, the workflows, and each page's markup, script and styles.
- Content is under Creative Commons Attribution 4.0 International
  ([LICENSE-CONTENT](LICENSE-CONTENT)): the words, numbers, data, images and screenshots each
  explorable presents, in its HTML and its README. To reuse it, credit kphutt and link to
  <https://explorables.kphutt.com/>.
- Fonts keep their own licenses, which are beside them in `pages/assets/fonts/`. Inter and
  Space Grotesk are under the SIL Open Font License 1.1.
- Pages link to the sources they cite. Those sources belong to their owners, and nothing here
  is affiliated with any company a page names.
