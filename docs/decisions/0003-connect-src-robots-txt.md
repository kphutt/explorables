# connect-src names robots.txt, and nothing else

## Status
Accepted. Changes one consequence of 0002, which said the policy was not to be loosened to
raise Lighthouse's SEO score.

## Context
Lighthouse scored SEO 92 on every page, with one failing audit: "Lighthouse was unable to
download a robots.txt file". The file serves fine. Lighthouse fetches it with the DevTools
command `Network.loadNetworkResource`, which runs from inside the page, so Chrome checks the
request against the page's `connect-src`. With `connect-src 'none'`, the fetch fails with a
CSP violation. Search crawlers fetch robots.txt directly and were never affected.

Lighthouse also fails robots.txt on any line it does not know, such as a `Content-Signal`
line.

## Decision
`connect-src` names exactly `https://explorables.kphutt.com/robots.txt`. A source with a path
matches only that exact path, so the page can fetch that one public file and nothing else.
`scripts/check.py` accepts that one source expression, or `'none'`, and fails anything
broader: `'self'`, the bare origin, a trailing slash, a wildcard, another scheme, another
path or another origin.

robots.txt has no `Content-Signal` line. Allowing everything is what robots.txt means when
nothing is disallowed, so the line added nothing.

## Consequences
- SEO is 100 on every page.
- A page's script could fetch robots.txt. It is public, and the request goes to this origin,
  so it reveals nothing and reaches nothing new.
- On any host other than explorables.kphutt.com (a deploy candidate's own URL, a local
  server), the URL does not match, and Lighthouse reports robots.txt as unreachable again.
