# Notes for Claude sessions

Venue map for EAGxBerlin 2026 (Urania Berlin): static mobile-first site + an import script that turns the Canva PDF into `data/overlay.json` and `maps/*.webp`.

- Read `docs/DEVELOPMENT.md` first (architecture, import pipeline, viewer layers, decisions, known gaps), then `README.md` (user guide + data contract).
- Never hand-edit `data/overlay.json` or `maps/`: change `import/overlay.overrides.json` (data fixes) or `scripts/import-config.json` (how the PDF is read) and re-run `python3 scripts/import.py`.
- `p/` and `maps/*-preview.jpg` are generated too: after editing `index.html` run `python3 scripts/pages.py`.
- Before committing: `node --check app.js` and `python3 scripts/validate.py`; check UI changes at phone size (390×780) in Playwright, light and dark.
- Keep README, `docs/DEVELOPMENT.md` (incl. "Decisions") and the schema in sync with behaviour changes.
- Never rename item ids (they end up in printed QR codes). `main` is live on GitHub Pages; work on a branch and fast-forward `main` when the owner asks.
- The owner isn't a software engineer: plain language, numbered points, copy-pasteable commands.
