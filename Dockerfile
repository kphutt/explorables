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
FROM ghcr.io/static-web-server/static-web-server:2.44.1@sha256:94618e3d17802265a21926217e6f9e7832b311b6fbf5933684001739fafed06a

COPY server/sws.toml /etc/sws.toml
COPY public/ /public/

ENV SERVER_CONFIG_FILE=/etc/sws.toml

USER 65534:65534

EXPOSE 8080
