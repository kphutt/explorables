# Backlog

<!-- One line per entry: a title that says the task, then the next step. Written for a public
reader: no local paths, no personal data, no private tracker links, no unfixed security findings.
Move an entry to Done when it ships. When Done grows long, move its older entries to
archive/done-YYYY-MM.md (one file per month). -->

## Blocked

## In progress

- **Move static-web-server off its beta.** It is on 3.0.0-beta.2, the only release that fixes
  GHSA-2fch-9x9r-mxmv. Next: move to 3.0.0-beta.3 once it is 7 days old (2026-11-18), which
  adds hardening for hidden files, OPTIONS requests and basic auth, or to 3.0.0 stable.
  kphutt.com's Dockerfile moves with it.
- **Remove explorables from kphutt.com's repository.** Next: merge kphutt.com's pull request
  that drops its old `explorables/` copy, its deploy jobs and its deployer's rights on this
  service, then apply it.

## Done

- **Tell IndexNow what each deploy changed**, as kphutt.com does, with this host's own key.
- **Live from this repository.** It is public, its settings are applied as code, and it
  deploys explorables.kphutt.com with its own identity and image repository. The first
  deploy passed the live smoke test, and Lighthouse scores it 100 on performance,
  accessibility, best practices and SEO.
- **Serve readable source, no minification.** backup-power is served as written, and the npm
  toolchain is gone (`docs/decisions/0002-serve-readable-source.md`). Earlier, its readable
  sources were added beside minified files, which terser and then esbuild produced.
- **Moved from kphutt.com's repository**, with the landing page, the server config, the gate
  and its tests, the container smoke test, the blue-green deploy and the rollback workflow.
