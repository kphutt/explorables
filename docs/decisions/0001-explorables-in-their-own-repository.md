# Keep explorables in their own repository

## Status
Accepted. The npm toolchain part is superseded by 0002.

## Context
Explorables started inside kphutt.com's repository, served from their own origin,
`explorables.kphutt.com`, by a second Cloud Run service. That repository's rule is that it has
no build tools beyond Hugo, and kphutt.com has no JavaScript at all.

An explorable needs its own toolchain. The first one, backup-power, ships minified files. Its
readable sources need a minifier (terser, from npm) and a check that the committed files are
exactly what the minifier makes from them. Adding npm and that check to the site's repository
would break its rule for the sake of pages it does not serve.

The infrastructure is a separate question. The explorables service, its image repository, the
domain mapping, the DNS record, the alerts and the cost cutoff share one OpenTofu state and one
Cloudflare zone with kphutt.com.

## Decision
Explorables live in this repository, with their own gate, tests, container, workflows and npm
toolchain. The infrastructure stays with kphutt.com's, in its `infra/`, and gives this
repository its own deploy identity: one that can push to the explorables image repository and
deploy the explorables service, and nothing of the site's.

## Consequences
- The site's repository keeps no JavaScript tooling, and this one can add what a page needs.
- The rules and the header policy were copied, not shared. A change to kphutt.com's
  Permissions-Policy has to be made here too (`PERMISSIONS_POLICY` in `scripts/check.py`).
- A change to the service, its domain or its identity is a pull request to the site's
  repository, reviewed and applied there.
