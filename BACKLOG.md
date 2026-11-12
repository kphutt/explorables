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
- **Remove explorables from kphutt.com's repository.** Next: after the first deploy from here,
  a pull request there that drops `explorables/`, its scripts and its deploy jobs.

## Done

- **backup-power: readable sources and a minify check.** The served files are proven to be
  exactly what `src/` minifies to, from a clean `npm ci`.
- **Moved from kphutt.com's repository**, with the landing page, the server config, the gate
  and its tests, the container smoke test, the blue-green deploy and the rollback workflow.
