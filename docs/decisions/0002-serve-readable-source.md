# Serve readable source, no minification

## Status
Accepted

## Context
backup-power was served minified, with its readable sources kept beside it in `src/` and a
check that the minified files were exactly what a minifier (terser, then esbuild) made from
them. That needed an npm toolchain: `package.json`, a lockfile, `.npmrc`, a pinned Node,
`npm ci` and `npm audit` in CI and at pre-push, and a Dependabot entry.

The server already compresses every text response with Brotli or gzip. Measured from
static-web-server 3.0.0-beta.2 with Brotli, backup-power's three files:

| File | Minified | Readable |
|---|---|---|
| `index.html` | 7,872 B | 8,036 B |
| `app.js` | 15,438 B | 20,041 B |
| `style.css` | 5,152 B | 5,603 B |
| **Total** | **28,462 B** | **33,680 B** |

Serving the readable files costs about 5 KB more on a first visit, and nothing on a cached
one.

## Decision
Pages are committed readable and served as they are. No minifier, no npm toolchain, no
`src/` copies.

## Consequences
- No npm supply chain: nothing is installed to build a page, and there is no lockfile, install
  script or registry to trust.
- The served code is the reviewed code. A reviewer reads exactly what a visitor's browser runs,
  and "View source" is readable.
- About 5 KB more per first visit for backup-power, after compression.
- Lighthouse may flag "Minify JavaScript" (and CSS). That is expected and accepted here.
- Lighthouse's SEO score is 92, not 100, on every page, because it fetches `robots.txt` from
  inside the page and `connect-src 'none'` blocks that; crawlers fetch it directly, so this is
  expected, and the policy is not to be loosened to chase it (kphutt.com scores 92 the same way).
- The gate still refuses a `src/` folder, `node_modules/`, `package.json`, a lockfile or a
  source map in the served output, so a build toolchain cannot come back by accident. Bringing
  one back is a new decision record.
