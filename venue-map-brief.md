# Venue map — build spec (v1, no editor)

EAGxBerlin 2026, Urania Berlin, 13–15 Nov 2026. Owner: Emily (Production). Written 2 Nov 2026.
Hand this to Claude Code as the brief. Ask Emily wherever this says **[ASK]**; do not guess.

## 1. Goal

A mobile-first web page attendees open from a QR code. It shows the venue floor plans. They tap a category (e.g. Toilets) and everything else dims, or search for a specific room / meeting point and the page jumps to it. Read-only for attendees. Desktop should work but is secondary.

Deadline: first working version by **Thu 5 Nov 2026**, so Emily can check it against the real building during the venue visit the week before the event. If that date slips badly, the project is dropped in favour of printed signage, so prefer a working simple version over a polished late one.

## 2. Inputs

- Floor plans from Canva, **one page per floor**, with labels and category colours already applied. Emily provides:
  - **PDF export (PDF Print, "Flatten PDF" unticked). This is the source of truth.** Confirmed: the labels are real, selectable text.
  - PPTX (presentation export) as a fallback only: it also carries shapes and text boxes with positions and fills. Use it only if the PDF's shapes turn out not to be vector paths, and tell Emily first.
  - PNG export: visual reference only, never a data source.
  - There is **no SVG export** (not available on Emily's Canva plan).
- A colour key (colour → category). **[ASK]** if not supplied or if the plans have no legend.
- Floor names/order (e.g. EG, 1. OG, …). **[ASK]**

## 3. Architecture: two layers, one owner each

| Layer | Contents | Source of truth |
|---|---|---|
| Base map | Floor outlines, room shapes, printed labels, colours | Canva PDF. Re-exporting replaces only the background files. |
| Overlay | Highlightable regions, pins, category, display name, search aliases, floor | `data/overlay.json` (generated once from the export, then hand-corrected) |

Rules:
- The viewer renders the base map as a background and the overlay on top. Keep them as **separate files**, so a later Canva re-export does not wipe overlay corrections, and so other tools (a laptop editor, or the layout planner, see §12) can write `overlay.json` later.
- The viewer reads **only** the final `data/overlay.json` and the background files it names. It never reads intermediate import files (`overlay.generated.json`, `overlay.overrides.json`, the report, anything in `scripts/`).
- Overlay coordinates are in each floor's own coordinate box (`width` × `height` in the JSON). For the Canva import that is the PDF page size in points. Emily must keep the Canva page size unchanged; note this in the README.
- No backend, no database, no login. Static files only.

## 4. Import pipeline (one-off script, re-runnable)

`scripts/import.py` (or Node, your choice; PyMuPDF is a good fit):
1. Read the PDF. Per page/floor, render a clean background yourself: WebP around 2000 px wide (or SVG via PyMuPDF if it comes out small). Also keep a high-res PNG per floor plus its pixel size in `source/` (not loaded by the page; see §12).
2. Extract text labels with positions from the PDF text layer.
3. Extract filled vector shapes and group them by fill colour → category via the colour key.
4. Match each shape to its nearest label to get a name.
5. Write `data/overlay.json` plus a **review report** (`import-report.md`) listing: shapes with no label, labels with no shape, colours not in the key, near-duplicate shades, and anything ambiguous. Do not silently guess; list it so Emily can answer in one pass.
6. Run the validation script (§5) on the result.

Re-running the script must not overwrite hand corrections. Either write to `overlay.generated.json` and merge with `overlay.overrides.json` into `overlay.json`, or diff and ask. Pick one and document it.

If the PDF's shapes are flattened or rasterised (text present but no usable vector fills), stop, tell Emily, and switch to the PPTX as the shape source.

Report back to Emily how much the import got right before polishing anything. If it is well below ~90%, stop and say so; the fallback is a laptop editor (out of scope for v1).

## 5. Data model (`overlay.json`, sketch)

```json
{
  "schemaVersion": 1,
  "updated": "2026-11-05T18:00:00+01:00",
  "floors": [
    { "id": "eg", "name": "EG", "order": 0, "background": "maps/eg.webp", "width": 1920, "height": 1080 }
  ],
  "categories": [
    { "id": "toilets", "label": "Toilets", "icon": "toilet", "color": "#..." }
  ],
  "items": [
    {
      "id": "mp-3",
      "floor": "eg",
      "category": "meeting-points",
      "name": "Meeting point 3",
      "aliases": ["MP3"],
      "shape": { "type": "polygon", "points": [[0,0],[10,0],[10,10]] },
      "pin": [5, 5]
    }
  ]
}
```

- `shape` may be `polygon` or `rect` (rooms, areas) or omitted for pin-only items. Every item has a `pin` for the jump-to marker.
- `categories[].floor` (optional): forces "selecting this category switches to that floor".
- Write a JSON Schema (`schema/overlay.schema.json`) and a small validation script that also checks references (item → floor, item → category, unique ids).
- The viewer ignores unknown fields instead of failing.

## 6. Categories

Confirmed by Emily:
- Toilets
- Food & snacks (food stations and snack points together)
- Meeting points
- Stairs
- Charging station (single location)
- Org fair (one floor only)
- Project fair (one floor only)
- Rooms (searchable by name; not necessarily a chip)

Proposed, **[ASK] before adding**: Lifts (step-free access, arguably belongs next to Stairs), Coat check, Registration, First aid, Quiet room.

Categories, their order, labels, colours and icons live in `overlay.json`, not in the viewer code. Icons come from a fixed built-in set chosen by name; unknown names fall back to a generic dot.

## 7. Viewer behaviour

- **Default:** current floor, everything visible at normal emphasis.
- **Floor switcher:** tabs at the top. Thumb-reachable on a phone.
- **Category bar:** horizontally scrollable chips at the bottom. Tap one: matching items on the current floor highlight, everything else (map and other items) dims. Tap again to clear. One category at a time is fine for v1.
  - If the selected category has nothing on the current floor, show which floors have it (e.g. "On 1. OG, 2. OG") as tappable links.
  - A category whose items are all on one floor (Org fair, Project fair), or that has `floor` set: selecting it **switches to that floor** automatically, then highlights. Derive this from the data; don't hard-code category names.
- **Search:** text field (open from an icon to save space). Matches name + aliases, case- and accent-insensitive. Searches the current floor by default with an "All floors" toggle; all-floor results show the floor name. Tapping a result switches floor, centres the item, and pulses its pin briefly.
- **Pan and pinch-zoom** on the map; double-tap to zoom; a reset button. Highlighting must stay correct at all zoom levels.
- **"Map updated <date, time>"** line visible somewhere unobtrusive, from `updated`. Attendees and volunteers should be able to tell how fresh it is.
- Deep links: `?floor=eg&cat=toilets` and `?item=mp-3`, so printed QR codes next to a sign can open a pre-filtered view. Keep the bare URL as the main QR target.

## 8. Mobile and performance

- Design for ~380 px wide first; check on a real iPhone and Android phone.
- Venue Wi-Fi with 700 people will be poor. Keep the initial page weight small (aim under ~1 MB), no frameworks needed, no external fonts or CDNs at runtime if avoidable.
- Load each floor's background only when that floor is first shown (the default floor loads immediately).
- Optional: a service worker for offline use **only if** it fetches fresh data when online. A cached stale map is worse than a slow one. If unsure, skip it.
- Respect `prefers-color-scheme`; text and highlight contrast must survive dimming. Don't rely on colour alone for categories: chips have icons + labels, highlighted items also get an outline.
- English UI. **[ASK]** whether German labels are wanted too.

## 9. Hosting

Static hosting with a **stable URL that never changes**, because it goes on printed QR codes. GitHub Pages or Netlify (free tier) are fine. **[ASK]** Emily which account/repo to use. Updating = edit files, push, same URL. Document the update steps in the README in plain language; Emily is not a developer.

## 10. Out of scope for v1

- The laptop editor (drag pins, set categories, publish). Keep the two-layer split so it can be added later.
- Any work on the layout planner (see §12; design constraint only).
- Live data, accounts, analytics, turn-by-turn routing, accessibility routing.
- Anything about other roles' content (session schedule, Swapcard). Comms (Dana) owns the attendee guide; Emily coordinates the QR placement.

## 11. Acceptance checklist

- [ ] All floors load; floor switch works on a phone with one thumb.
- [ ] Each category chip dims everything else and highlights only that category.
- [ ] Org fair / Project fair jump to their floor.
- [ ] Search finds every named room and meeting point; "All floors" toggle works; tapping a result jumps and pulses.
- [ ] Empty-category state points to the floors that have it.
- [ ] Works at 380 px width, light and dark mode, with pinch-zoom.
- [ ] "Map updated" timestamp shown.
- [ ] Initial load under ~1 MB; other floors load on demand.
- [ ] `overlay.json` passes the validation script.
- [ ] Import report reviewed by Emily; no unresolved items.
- [ ] Deployed at a stable URL; README explains how to update, the "don't change Canva page size" rule, and the data contract (§12).
- [ ] Emily has walked the venue with it and confirmed positions match reality.

## 12. Future integration with the layout planner (design constraint, do NOT build)

Later, a separate internal tool (the "layout planner", a React/Konva app with its own floor plans, named polygon zones and point markers in plan-image pixels) may get an "Export attendee map" add-on that writes this viewer's data files. Nothing planner-side is in scope now. Keep the viewer generic enough that a second producer can feed it:

1. **`data/overlay.json` is the only contract** (§3). The import pipeline is one producer of it, not part of the viewer.
2. **Versioned and validated** (`schemaVersion`, JSON Schema, validation script; §5). Unknown fields are ignored, so a producer may add extras such as `"pxPerMeter"` or `"source": "planner"`.
3. **Coordinates are whatever each floor says.** The background is stretched to fill the floor's `width` × `height` box (an SVG `viewBox="0 0 width height"`). Don't assume PDF points, a fixed size, or the same size on every floor. A producer using raster pixels (e.g. 4961×3508) and one using PDF points must both work unchanged.
4. **Background format is not fixed:** accept `.svg`, `.png` and `.webp` per floor, chosen by file extension.
5. **Nothing venue-specific in the code:** floors, categories, labels, colours, icons and "category lives on one floor" all come from the data (§6, §7).
6. **Ids are opaque, stable strings.** They are used in deep links and printed QR codes, so they never change once published. Don't parse meaning out of them or rely on them being short slugs.
7. **Shapes:** only `polygon` and `rect`. Anything else is the producer's job to convert. `pin` is always present; when a producer has none, the producer computes it (e.g. polygon centroid), not the viewer.
8. **Raster copy kept:** the per-floor high-res PNG plus pixel size in `source/` (§4), so the same base map and overlay can later be loaded into the planner 1:1.
9. **README "Data contract" section:** the files the viewer reads, the schema location, and the rule that any tool may regenerate `overlay.json` and `maps/` as long as it passes the validation script.

None of this may delay the Thu 5 Nov version. If a point costs more than a few minutes, note it in the README as a known gap and move on.
