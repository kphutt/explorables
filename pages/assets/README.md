# Shared assets

Files more than one page uses, served from `/assets/`. This folder is not an explorable: it
is not in the sitemap and holds no page (`scripts/check.py` fails if it does).

- `fonts/`: Inter and Space Grotesk, variable `woff2`, each beside its SIL Open Font License
  file. The landing page, the 404 page and backup-power load them from here, so a visitor
  downloads each font once.
- `previews/`: the landing page's card images, one per explorable. `backup-power.jpg` is cut
  from that explorable's own screenshot.
