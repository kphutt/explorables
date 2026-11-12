# The explorables container: static-web-server plus the checked pages, nothing else.
#
# CI copies pages/ into public/ without its READMEs or readable sources, adds the generated
# robots.txt and sitemap.xml, runs scripts/check.py on that exact output, then copies it in
# here. Build it the same way locally:
#
#     python scripts/build.py && python scripts/check.py public
#     docker build -t explorables . && docker run --rm -p 8080:8080 --read-only explorables
#     python scripts/smoke.py http://127.0.0.1:8080
#
# Pinned by version and digest, which scripts/check.py requires. It is the same image
# kphutt.com is served from; Dependabot proposes updates here, and each one gets the same
# container smoke test as any other change.
#
# A beta on purpose: 3.0.0-beta.2 is the only release that fixes GHSA-2fch-9x9r-mxmv (idle
# connections were never closed). Move to 3.0.0 stable as soon as it is out and past the
# 7-day wait. v3 renamed some config keys (server/sws.toml says which).
FROM ghcr.io/static-web-server/static-web-server:3.0.0-beta.2@sha256:dd6db18272872154f1d287cc5b565626379339c34171263aa0a97b68c78f4ac3

COPY server/sws.toml /etc/sws.toml
COPY public/ /public/

ENV SERVER_CONFIG_FILE=/etc/sws.toml

USER 65534:65534

EXPOSE 8080
