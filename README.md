# Venue map (EAGxBerlin 2026, Urania Berlin)

A phone-friendly page attendees open from a QR code. It shows the floor plans; tapping a category (Toilets, Food & snacks, Meeting points, …) dims everything else, and search jumps to a room or meeting point.

Static files only: no server, no database, no login. Brief: [`venue-map-brief.md`](venue-map-brief.md).

**Status (2 Nov 2026):** first working version, reviewed once. Decisions so far are recorded in `import/overlay.overrides.json` (`_decisions`). Hosting: GitHub Pages (repo public for now).

---

## Using it

- **Floors**: tabs at the top. A dot on a tab means the selected category exists on that floor (including the one you're on).
- **Categories**: chips at the bottom. Tap = highlight, tap again = clear. Org fair and Project fair jump to their floor automatically.
- **Room list**: open search without typing: all rooms, grouped by floor (coloured bar per floor), opened at the floor you're on.
- **Search**: magnifier, top right. Finds names, codes (`C3`, `MP C3`), descriptions (`speaker` → Darwin). Accents and case don't matter. "All floors" (on by default) lists/searches the whole building, grouped by floor and opened at the floor you are on (it follows when you switch floors); untick it for this floor only. Typed results list this floor first. With a category selected (e.g. Meeting points), search opens showing just that category, grouped by floor; untick "Only Meeting points" to search everything. Enter opens the first result.
- **Card** at the bottom floats over the map (opening/closing it never moves the map).
  - Tap its round icon to bring everything selected on this floor into view (zooms out only as far as needed), or to jump back to the selected item.
  - On an item: **Share** (phones; *Copy link* on desktop) sends a link that opens the map on that spot, e.g. "meet me at C3". "All …" highlights the whole category.
  - Nothing of that category on this floor: the card says so in red, and the floors that have it are buttons.
- Selecting a category while zoomed into a part of the floor where none of them are moves the map so they're in view.
- **Tap a printed label** (e.g. *Nap Rooms*) to select that thing; tapping the *Organisations Fair* title selects the whole Org fair.
- **Floor tabs**: the current floor has a thin outline in that floor's colour; tapping it again shows the whole floor. Switching floor automatically (from search or a category) shows a short "Switched to …" message.
- **Tap anything on the map** to see what it is.
- **Colours** on the plan are muted. While something is selected, everything else turns grey (labels, pins, coloured areas) and only the selection keeps its colour; the plan's walls and outlines stay as they are. Add `&outline=1` to the URL to also draw an outline around selected areas (for comparison).
- **Org fair**: the printed boxes only show while Org fair is selected. Of the three arrows from the *Organisations Fair* title only the middle one is shown (`hiddenArrows` in `scripts/import-config.json`).
- **Labels**: with something selected, only its labels stay crisp and the rest fade. The **Aa** button (top right of the map) shows every label exactly as printed in the PDF; the choice is remembered on that phone.
- **Zoom**: pinch, double-tap, mouse wheel; the corner button resets.
- **Links for printed QR codes** (open a pre-filtered view):
  - `…/?floor=1&cat=toilets` (floor 1, toilets highlighted)
  - `…/?item=mp-c3` (jumps to meeting point C3)
  - The bare URL stays the main QR target.
  - Item ids are listed in `data/overlay.json` and in the review pictures (`import/review/*.jpg`). **Never rename an id that has been printed.**

## Updating the map

Two kinds of change.

### A. The floor plans changed in Canva

1. In Canva: **File → Download → PDF Print**, with **"Flatten PDF" unticked**. **Do not change the Canva page size** (all positions are measured on the page; a different size moves every highlight).
2. Replace `source/attendee-map.pdf` with the new file (same name).
3. Run the import (needs Python 3 once: `pip install -r scripts/requirements.txt`):

   ```bash
   python3 scripts/import.py
   ```

4. Read `import/import-report.md` and look at `import/review/*.jpg`. Fix anything wrong via step B.
5. Commit and push. The URL stays the same.

Easiest if you're not at a terminal: ask Claude Code to "re-run the attendee map import with the new PDF, show me the report, and push".

### B. Correct something the import got wrong

Never edit `data/overlay.json` by hand; the next import overwrites it. Corrections go in **`import/overlay.overrides.json`**, which the import never touches:

```json
{
  "items": {
    "room-outside-area-1-1s": { "name": "Outside Area", "description": "1:1s" },
    "stairs-1-3": null,
    "mp-c3": { "aliases": ["Cafeteria meeting point"] }
  },
  "add": [
    { "id": "first-aid-0", "floor": "0", "category": "first-aid", "name": "First aid", "pin": [300, 700] }
  ],
  "categories": { "lifts": { "enabled": true } },
  "categoryOrder": ["toilets", "food", "meeting-points"],
  "floors": { "0": { "shortName": "EG" } }
}
```

- `"some-id": { … }` changes only the fields given; `"field": null` removes that field.
- `"some-id": null` removes the item.
- `add` adds items the import can't see (positions are in PDF points: the page is 843 × 1191, top-left is 0,0; the review pictures help to estimate).
- `categories` changes or adds categories; `"enabled": false` hides a category and all its items.
- Then run `python3 scripts/import.py` again (it merges and validates).

## How the import works

`scripts/import.py`, settings in `scripts/import-config.json`.

| Thing on the map | Where it comes from | Reliability |
|---|---|---|
| Room names, descriptions | Visible text in the PDF | High. Hidden text behind the plan picture is ignored and reported. |
| Meeting points | The orange pins + the nearest "Point …" label | High (17/17). Long arrows are flagged. |
| Catering, Project fair | Dark-blue pins + nearest label | High |
| Org fair areas | Outlined boxes drawn in Canva | High |
| Charging station | End of the arrow from its label | Check on site |
| Toilets, stairs, lifts, stages | **Colour in the floor-plan picture**, using the legend colours (+ the cream spiral staircases) | Good, but check: the plan is one picture in the PDF, not shapes |
| Room outlines | Flood-fill of the white floor around each label. Labels outside the building (e.g. *Nap Rooms*) follow their thin lines to the room(s) they point at | Partial: open-plan areas get a pin only |

Areas painted over by a box in Canva (e.g. a lift hidden with a grey box) are left out and reported.

Files it writes:

- `maps/<floor>.webp`: the plan picture with colours muted (walls untouched). Loaded first. (The grey copies used while something is selected are made by the browser from this file and the labels file; nothing extra to download.)
- `maps/<floor>-labels.webp`: everything you drew in Canva (text, pins, arrows, boxes), on a transparent background, separated from the plan picture. Loaded first.
- `maps/<floor>-full.webp`: the plan picture in full colour; only fetched when something on that floor is highlighted, and only shown inside the highlighted shapes.
- Solid grey/white boxes drawn in Canva over the plan (e.g. hiding closed areas) are painted into the plan layers, so they are muted and dimmed with the plan and fading labels never reveals what they cover. Boxes that don't actually show in the PDF are ignored.
- `source/raster/<floor>.png` + `source/raster/rasters.json`: high-res copies with pixel sizes, kept for the layout planner (not loaded by the page).
- `import/overlay.generated.json`: raw import result.
- `data/overlay.json`: generated + overrides. **This is what the page reads.**
- `import/import-report.md`, `import/review/*.jpg`: for review.

## Data contract

For any other tool that wants to produce this map (the layout planner, a future editor):

1. The page reads **only** `data/overlay.json` plus the background files it names. Nothing in `import/`, `scripts/` or `source/`.
2. Format: [`schema/overlay.schema.json`](schema/overlay.schema.json), `schemaVersion: 1`. Unknown fields are ignored, so producers may add extras (`"source": "planner"`, `"pxPerMeter"`, …).
3. Coordinates are in each floor's own box (`width` × `height`); the background is stretched to fill it. PDF points, raster pixels, anything works, and floors may differ.
4. Backgrounds can be `.svg`, `.png`, `.webp` (or `.jpg`), per floor.
5. Floors, categories, labels, colours, icons and order all come from the data. Nothing venue-specific is in the code. A category whose items are all on one floor (or that sets `"floor"`) switches to that floor when selected.
6. Ids are opaque, stable strings (they end up in printed QR codes).
7. Shapes: `polygon` or `rect` only. Every item has a `pin` (the producer computes one if needed).
8. Optional extras the viewer understands: `floor.shortName` (tab label), `floor.color` (bar in the room list), `item.shapes` (several areas for one item, e.g. four nap rooms), `floor.view` (`[x, y, w, h]` start view), `category.chip: false` (searchable, no chip), `item.description`.
   Layers (all optional; without them the page dims the whole background instead):
   - `floor.backgroundHighlight`: full-colour image, shown only inside highlighted shapes (so `background` can be muted);
   - `floor.labels`: transparent image of printed labels drawn on top;
   - `item.labelBoxes`: `[x, y, w, h]` boxes where an item's printed label/pin sits in that image (kept crisp when the item is highlighted, faded otherwise);
   - `floor.chromeBoxes`: title/legend areas, faded unless *All labels* is on;
   - `item.labelsWhenSelected`: shapes in the label image shown only while that item (or its category) is selected (e.g. the Org fair boxes);
   - `floor.hiddenLabels`: shapes in the label image never shown, except with *All labels* (e.g. unwanted arrows);
   - `floor.fixedBoxes`: areas of the label image that are always fully shown.
9. **Any tool may regenerate `data/overlay.json` and `maps/` as long as `python3 scripts/validate.py` passes.**

Icon names available: `toilet food pin stairs bolt booth flask door lift stage info coat firstaid quiet registration` (anything else shows a dot).

## Hosting

Any static host works; the site is the repository root (`index.html`, plus an empty `.nojekyll`).

Current plan: **GitHub Pages**, repo public. Settings → Pages → *Deploy from a branch* → `main`, folder `/ (root)`. URL: `https://supernovaria.github.io/attendee-map/`.

If the repo goes private later, Cloudflare Pages can deploy from a private repo (the site itself stays public). **Moving host changes the URL and breaks printed QR codes**, so either settle the host before printing, or put the QR codes on a domain you control (e.g. a subdomain pointed at whichever host) so the host can change underneath.

## Known gaps

- Room outlines exist for about half the rooms; the rest highlight as a pin. Fine for search; add a `rect`/`polygon` via overrides where it matters.
- No offline mode (deliberately: a stale cached map is worse than a slow one).
- English UI only (decided).
- Stages are extracted but switched off (`categories` in the overrides to turn on).
- Toilets inside the Nap Rooms wing (ground floor) are not coloured on the plan, so they're not in the Toilets category.
