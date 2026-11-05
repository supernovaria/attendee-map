# Venue map (EAGxBerlin 2026, Urania Berlin)

A phone-friendly page attendees open from a QR code. It shows the floor plans; tapping a category (Toilets, Food & snacks, Meeting points, …) dims everything else, and search jumps to a room or meeting point.

Static files only: no server, no database, no login. Brief: [`venue-map-brief.md`](venue-map-brief.md). How it's built and why (for whoever works on it next): [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

**Status (3 Nov 2026):** first working version, reviewed once; Share tested on a phone. Decisions so far are recorded in `import/overlay.overrides.json` (`_decisions`). Hosting: GitHub Pages (repo public for now).

---

## Using it

- **Floors**: tabs at the top. A dot on a tab means the selected category exists on that floor (including the one you're on).
- **Categories**: chips at the bottom. Tap = highlight, tap again = clear. Org fair and Project fair jump to their floor automatically.
- **Room list**: open search without typing: all rooms, grouped by floor (coloured bar per floor), opened at the floor you're on.
- **Search**: magnifier, top right. Finds names, codes (`C3`, `MP C3`), descriptions (`speaker` → Darwin) and everyday words (`WC`, `elevator`, `coat`, `lunch`, `kids`; set as `aliases` on items and categories in the overrides). Accents and case don't matter. "All floors" (on by default) lists/searches the whole building, grouped by floor and opened at the floor you are on (it follows when you switch floors); untick it for this floor only. Typed results list this floor first. With a category selected (e.g. Meeting points), search opens showing just that category, grouped by floor; untick "Only Meeting points" to search everything. Enter opens the first result.
- **Card** at the bottom floats over the map (opening/closing it never moves the map).
  - Selecting a room (search, link, or tapping it) briefly draws its outline. The map zooms in only as far as the whole room still fits, so a big room like the Arnheim-Foyer looks big.
  - Tap its round icon to bring everything selected on this floor into view (zooms out only as far as needed), or to jump back to the selected item. An outline is drawn around each of them (a circle for things that are only a pin), stays a moment, then fades.
  - Until the round icon has been tapped once on a phone, it shows a few soft rings each time something is selected, as a hint (remembered in the browser: `venueMap.dotSeen`).
  - A selected room gets a marker standing on top of its printed name (never over it); the ripple only plays for things that have no highlighted shape.
  - A selected meeting point gets no marker: its printed pin already shows the exact spot, so the ripple plays round that pin instead.
  - On an item: **Share** (phones; *Copy link* on desktop) sends a link that opens the map on that spot, e.g. "meet me at C3". "All …" highlights the whole category. Some items have extra buttons that open a web page (`links`), e.g. **Directions** on the Main entrance.
  - Catering shows its meal times (the item's `description`).
  - **How to get here from the … floor**: shown when you jumped to the item from another floor (search, a link) or when a "You are here" dot is on another floor. It shows the floor you come from with the lifts and stairs that go to the item's floor highlighted (with a "You are here" dot: only the nearest lift and the nearest stairs), says "Take the lift or the stairs up to the 2nd floor", and has a button to go there. If the stairs only go part of the way, it says where to change. Which floors a lift/staircase reaches is `connects` in the data (read from the "To floor …" notes and lift numbers in the PDF; 2nd-floor stairs set in the overrides).
  - Nothing of that category on this floor: the card says so in red, and the floors that have it are buttons.
- Selecting a category while zoomed into a part of the floor where none of them are moves the map so they're in view.
- **Tap a printed label** (e.g. *Nap Rooms*) to select that thing; tapping the *Organisations Fair* title selects the whole Org fair.
- **Floor tabs**: the current floor has a thin outline in that floor's colour; tapping it again shows the whole floor. Switching floor automatically (from search or a category) shows a short "Switched to …" message.
- **Tap anything on the map** to see what it is.
- **Colours** on the plan are muted. While something is selected, everything else turns grey (labels, pins, coloured areas) and only the selection keeps its colour; the plan's walls and outlines stay as they are. A selected room is marked like with a highlighter (pale blue in light mode, blue-grey in dark mode); its walls, doors and text keep full contrast. Add `&outline=1` to the URL to also draw an outline around selected areas (for comparison).
- **Org fair**: the printed boxes only show while Org fair is selected. Of the three arrows from the *Organisations Fair* title only the middle one is shown (`hiddenArrows` in `scripts/import-config.json`; the import removes the others from the label image).
- **Labels**: with something selected, only its labels stay crisp and the rest fade. The **Aa** button (top right of the map) shows every label exactly as printed in the PDF; the choice is remembered on that phone.
- **Colours**: the round button under **Aa** switches between *automatic* (half circle: light or dark like the phone), *light* (sun) and *dark* (moon). In dark the map itself is dark too: white paper turns dark grey, black walls and text turn light, the coloured areas keep their colours. Remembered on that phone.
- **Zoom**: pinch, double-tap, mouse wheel; the corner button resets.
- **Links for printed QR codes** (open a pre-filtered view):
  - `…/?floor=1&cat=toilets` (floor 1, toilets highlighted)
  - `…/?item=mp-c3` (jumps to meeting point C3)
  - `…/?here=mp-c3` (**You are here**: for a QR code on a sign at that spot. Opens that floor zoomed in around a blue dot with a "You are here" tag; the tag disappears after 8 seconds so it doesn't hide printed labels, the dot stays while browsing. Selecting a category keeps the dot in view if it has to move the map. Any item id works; can be combined, e.g. `?here=mp-c3&cat=toilets`.)
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
| Room outlines | Traced from the plan around each label: walls are followed with square corners, doorways are cut along the wall line, door swings count as part of the room. Open areas with no wall between two rooms are split by *dividers* in `scripts/import-config.json` (`roomShapes.dividers`, e.g. the 3rd-floor Foyer/Voltaire pillar row). Labels outside the building (e.g. *Nap Rooms*) follow their thin lines to the room(s) they point at | Good. A few outlines are still hand-drawn in the overrides (Kleist Hall, Registration, Main entrance, Spontaneous Conversation Area) |

Areas painted over by a box in Canva (e.g. a lift hidden with a grey box) are left out and reported.

Files it writes:

- `maps/<floor>.webp`: the plan picture with colours muted (walls untouched). Loaded first. (The grey copies used while something is selected are made by the browser from this file and the labels file; nothing extra to download.)
- `maps/<floor>-labels.webp`: everything you drew in Canva (text, pins, arrows, boxes), on a transparent background, separated from the plan picture. Loaded first.
- `maps/<floor>-full.webp`: the plan picture in full colour; only fetched when something on that floor is highlighted, and only shown inside the highlighted shapes.
- `maps/<floor>-dark.webp`, `maps/<floor>-full-dark.webp`, `maps/<floor>-labels-dark.webp`: the same three for dark mode (only downloaded by phones in dark mode). How dark: `"dark"` in `scripts/import-config.json` (`floor` should match `--map-bg` in `style.css`). In the dark labels picture the printed meeting-point pins get a thin white outline (`pinOutline`, `pinOutlinePx`), so their pale needle shows on the dark floor.
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
8. Optional extras the viewer understands: `floor.shortName` (tab label), `floor.color` (bar in the room list), `item.shapes` (several areas for one item, e.g. four nap rooms), `floor.view` (`[x, y, w, h]` start view), `category.chip: false` (searchable, no chip), `category.marker: false` (no extra marker on a selected item, because the plan prints its own pin; meeting points), `item.description`, `category.aliases` (extra search words for every item of the category, e.g. `WC`), `item.links` (`[{"label": "Directions", "url": "https://…"}]`: buttons on the item's card; https only), `item.connects` (stairs/lifts: ids of the other floors they go to; used by *How to get here*).
   Layers (all optional; without them the page dims the whole background instead):
   - `floor.backgroundHighlight`: full-colour image, shown only inside highlighted shapes (so `background` can be muted);
   - `floor.labels`: transparent image of printed labels drawn on top;
   - `item.labelBoxes`: `[x, y, w, h]` boxes where an item's printed label/pin sits in that image (kept crisp when the item is highlighted, faded otherwise);
   - `floor.chromeBoxes`: title/legend areas, faded unless *All labels* is on;
   - `item.labelsWhenSelected`: shapes in the label image shown only while that item (or its category) is selected (e.g. the Org fair boxes);
   - `floor.hiddenLabels`: shapes in the label image never shown, except with *All labels* (fallback for unwanted arrows the import couldn't remove from the PDF drawing; normally absent);
   - `floor.fixedBoxes`: areas of the label image that are always fully shown;
   - `floor.dark`: `{background, backgroundHighlight, labels}` dark-mode versions of those pictures (same size); each missing one falls back to the light picture.
9. **Any tool may regenerate `data/overlay.json` and `maps/` as long as `python3 scripts/validate.py` passes.**

Icon names available: `toilet food pin stairs bolt booth flask door lift stage info coat firstaid quiet registration` (anything else shows a dot).

## Hosting

Any static host works; the site is the repository root (`index.html`, plus an empty `.nojekyll`).

Current plan: **GitHub Pages**, repo public. Settings → Pages → *Deploy from a branch* → `main`, folder `/ (root)`. URL: `https://supernovaria.github.io/attendee-map/`.

If the repo goes private later, Cloudflare Pages can deploy from a private repo (the site itself stays public). **Moving host changes the URL and breaks printed QR codes**, so either settle the host before printing, or put the QR codes on a domain you control (e.g. a subdomain pointed at whichever host) so the host can change underneath.

## Known gaps

- Every room has an outline except *Outside Area 1:1s* (highlights as a pin). Outlines can be added or corrected with a `rect`/`polygon` via overrides; where two rooms share an open area, a divider line in `scripts/import-config.json` (`roomShapes.dividers`) is usually the better fix, because the import then traces both rooms itself.
- No offline mode (deliberately: a stale cached map is worse than a slow one).
- English UI only (decided).
- Stages are extracted but switched off (`categories` in the overrides to turn on).
- Toilets inside the Nap Rooms wing (ground floor) are not coloured on the plan, so they're not in the Toilets category.
