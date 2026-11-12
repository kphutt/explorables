# Backlog

<!-- One line per entry: a title that says the task, then the next step. Written for a public
reader: no local paths, no personal data, no private tracker links, no unfixed security findings.
Move an entry to Done when it ships. When Done grows long, move its older entries to
archive/done-YYYY-MM.md (one file per month). -->

## Blocked

- **First deploy from this repository.** Waits on the owner: create the GitHub repository and
  its settings, and apply kphutt.com's infrastructure change that gives this repository its
  own deploy identity.

## In progress

- **First deploy from this repository.** Next: once the repository and its deploy identity
  exist, set the `cloud-run` environment and the repository variables, merge to `main`, and
  confirm the deploy and the live smoke test.
- **Move static-web-server off its beta.** It is on 3.0.0-beta.2, the only release that fixes
  GHSA-2fch-9x9r-mxmv. Next: move to 3.0.0-beta.3 once it is 7 days old (2026-11-18), which
  adds hardening for hidden files, OPTIONS requests and basic auth, or to 3.0.0 stable.
  kphutt.com's Dockerfile moves with it.
- **Remove explorables from kphutt.com's repository.** Next: after the first deploy from here,
  a pull request there that drops `explorables/`, its scripts and its deploy jobs.

## Done

- **Serve readable source, no minification.** backup-power is served as written, and the npm
  toolchain is gone (`docs/decisions/0002-serve-readable-source.md`). Earlier, its readable
  sources were added beside minified files, which terser and then esbuild produced.
- **Moved from kphutt.com's repository**, with the landing page, the server config, the gate
  and its tests, the container smoke test, the blue-green deploy and the rollback workflow.
