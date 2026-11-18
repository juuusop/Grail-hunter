# Grail Atlas (site)

The finds browser for the scanner, published as a claude.ai Artifact.

    python atlas/build_page.py . OUT/atlas.html ATLAS_IMAGES_CHECKOUT

- `atlas_template.html`: markup + styles, `atlas_app.js`: the app; both are inlined with the data JSON into one page.
- Pictures ship next to the page: `img/sN.jpg` (120 px sprites) and `hi/hN.webp` (360 px sheets from the `atlas-images` branch).
  Publish all of them with the page (max 255 files per publish, so split over two).
- Views: Etusivu, Löydöt (faceted filters, category tree, brand picker, sizes), Brändit (brand guide), Poiminnat,
  Tallessa (hearts, per browser), Logiikka. Item and brand pages open as sheets, so the list and its filters never reset.
- Filters, sort, loaded rows and scroll per view are kept in localStorage (`atlas-state-v2`, migrates `atlas-state-v1`).
- `notes.py` (brand notes) and `picks.py` (curator picks) feed the "why" lines.

## Public copy (GitHub Pages)

`.github/workflows/atlas-site.yml` builds the same page hourly and force-pushes it to the `gh-pages` branch, served at
https://juuusop.github.io/grail-hunter/ so people without claude.ai access can use it. Saved filters and hearts stay per browser.
