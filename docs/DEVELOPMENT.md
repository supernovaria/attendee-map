# Developer notes

For whoever works on this next: a person, or a future Claude session. It explains how the pieces fit together, why things are the way they are, and the traps already found. The user-facing guide (how to use it, how to update the map, the data contract) is [`README.md`](../README.md); the original brief is [`venue-map-brief.md`](../venue-map-brief.md). Don't repeat README content here; update both when behaviour changes.

Status as of 3 Nov 2026 (evening): first version live on GitHub Pages (`https://supernovaria.github.io/attendee-map/`), deployed from `main`, root folder. Built for EAGxBerlin 2026 at Urania Berlin. Production lead and owner: the repo owner (supernovaria).

---

## 1. The shape of the project

```
source/attendee-map.pdf ──► scripts/import.py ──► data/overlay.json ──► index.html + app.js + style.css
   (Canva export)            (+ import-config.json,   + maps/*.webp        (static viewer, no build step)
                              overlay.overrides.json)
```

- **Two layers, one contract.** The viewer reads only `data/overlay.json` and the images it names. Anything that can write that file (the import, a future layout planner, a hand-made file) can drive the map. Schema: `schema/overlay.schema.json`; extra checks: `scripts/validate.py`.
- **No framework, no build, no external requests.** Plain ES2020 in one IIFE (`app.js`), one stylesheet, one HTML file. Keep it that way unless there is a strong reason: the site must load fast on a phone on venue Wi-Fi from a QR code. Initial load is about 200 KB (JSON + muted plan + labels image for one floor).
- **Venue-agnostic code.** Floors, categories, colours, icons and order all come from the data. Venue-specific knowledge lives in `scripts/import-config.json` (how to read *this* PDF) and `import/overlay.overrides.json` (hand corrections).

### Files

| Path | What | Edited by hand? |
|---|---|---|
| `index.html`, `app.js`, `style.css` | The viewer | yes |
| `data/overlay.json` | What the viewer reads | **no**, generated (generated + overrides) |
| `maps/<floor>.webp` | Plan picture, colours muted | no, generated |
| `maps/<floor>-full.webp` | Plan picture, full colour (shown only inside selected shapes) | no, generated |
| `maps/<floor>-labels.webp` | Everything drawn in Canva, transparent background | no, generated |
| `scripts/import.py` | PDF → data + images | yes |
| `scripts/import-config.json` | How to read this particular PDF (colours, label rules, ignore lists, hidden arrows …) | yes |
| `import/overlay.overrides.json` | Hand corrections merged over the import; also `_decisions` (what the owner decided and when) | yes |
| `import/overlay.generated.json` | Raw import result (for diffing) | no |
| `import/import-report.md`, `import/review/*.jpg` | What the import found, what to check | no |
| `source/raster/*` | High-res PNGs + `rasters.json` for a future layout planner (not loaded by the site) | no |
| `source/*.pptx` | Older source of the floor plan (reference only, not used by the import) | – |
| `schema/overlay.schema.json`, `scripts/validate.py` | Data contract | yes, keep in sync with the viewer |

---

## 2. The import (`scripts/import.py`)

Run: `pip install -r scripts/requirements.txt` once, then `python3 scripts/import.py` from the repo root. It ends by running the validator. It is deterministic: unchanged PDF ⇒ unchanged images and JSON (except the `updated` timestamp).

### What the PDF looks like (important)

The Canva file was exported through Firefox's PDF viewer. Each page is:

1. one **embedded raster image** of the architect's floor plan (with toilets, stairs, lifts, stages coloured *in the pixels*; no vector shapes), plus
2. **Canva vector drawings and text on top**: room names, meeting-point pins, arrows, org-fair boxes, grey/white boxes hiding closed areas, title, legend,
3. some **stale text and drawings hidden behind the image** (drawn before it). These must be ignored.

Coordinates everywhere are **PDF points of the page** (843 × 1191). That is why the README says *never change the Canva page size*.

### Pipeline per floor (numbered like the comments in `main()`)

1. **Backgrounds.** `plan_canvas` warps the embedded image onto the page grid; this is the "plan only" picture used for colour detection and room outlines.
2. **Vector data.**
   - Hidden-vs-visible is decided by draw order: a text span or drawing whose `seqno` is lower than a covering image's and lies inside it is hidden (`covering_images`, `is_hidden`, `visible_lines`). Zero-width characters are stripped.
   - `group_blocks`: label = leading lines at the largest font size; the rest is the description.
   - 2a. Meeting points: orange pins (`find_pins`) greedily matched to the nearest "Point …" label.
   - 2b. Navy pins → Catering / Project fair by nearest label.
   - 2c. Outlined boxes with a coloured stroke (`find_outlined_areas`) → Org/Project fair areas. Categories listed in `boxesOnlyWhenSelected` get `labelsWhenSelected` (the box footprint), so the viewer hides the printed box unless selected. Anything else printed that touches the box (arrow tips, lines, letters: `things_on`) is cut out of that footprint so it isn't clipped, but the box's own outline stays hidden there (`always` in `footprint`).
   - 2d. Charging and leftover category labels → pin at the label (or the end of its arrow).
3. **Colour areas.** `colour_regions` on the plan-only picture, colours from `rasterKey` in the config (toilets, stairs, lifts, stages, cream spiral stairs). `ignoreRaster` lists known false positives. Areas under Canva grey boxes (`canva_covers`) are excluded and reported as closed.
4. **Rooms.**
   - Outline of the room around each label (`room_shape` → `room_mask`; settings in `roomShapes` in the config). `floor_masks` sorts the plan's pixels once per floor: **walls** = grey areas thicker than `thinLinePt`, plus long thin lines darker than `thinWallDarkerThan` (the Nap Rooms wing has 1 pt dark walls); light thin lines (door leaves and swings, window frames) are *door lines*; stage colour (`floorColours`) and its outline/tiles count as floor; **outside** = white connected to the page edge. Then, per room:
     1. Squares of side 2×`doorPt` are fitted into the floor with door lines still closed. Each connected group of them is a room, so doorways narrower than the square keep rooms apart (this replaces the old erode/dilate with a disc, which rounded every corner and stepped around door swings).
     2. Each room then claims the floor nearest to it with door lines ignored (`grow_labels`), so door swings and seat rows belong to the room.
     3. Bits narrower than 2×`openingPt` sticking out (doorways) are cut along the wall line; slots narrower than 2×`slotPt` (wall stubs, pillars) are filled.
     The squares are turned to the walls around the room (`wall_angles`: straight wall edges, weighted by length; the ground floor's wings are at about 21°). A room between walls at two angles (the cafeteria) gets both results combined. Rooms bigger than `maxPageShare` of the page are taken as open areas (pin only).
   - `roomShapes.perRoom` (by printed name) sets a smaller square for open foyers whose narrow corridors belong to them (3rd-floor Foyer, Arnheim-Foyer).
   - `roomShapes.dividers` are lines drawn in as walls before tracing, for open areas the plan has no wall between: Humboldt Hall/Cafeteria, Edison/2nd-floor foyer, 3rd-floor Foyer/Voltaire.
   - Labels **outside the building** (Nap Rooms, Prayer Room, Parents Room) follow their thin leader lines. The lines are found by Hough on the label layer (`leader_targets`). From the line's end, `behind_wall` steps through the wall and `room_near` takes the room found there (same tracer, with the smaller `smallDoorPt`/`smallOpeningPt`); failing that, it takes the nearest indoor room to the line's end. One item can therefore have several `shapes`.
5. "To floor …" notes and lift digits become `labelBoxes` of the nearest stairs or lift.
6. **Layers.** C = page render, B = plan-only render (Canva cover boxes painted in, title strip blanked). `uncomposite(C, B)` solves *F over B = C* for an RGBA layer F: that's `-labels.webp`. `mute(B)` desaturates/lightens saturated pixels only (walls stay black) → `<floor>.webp`. B itself → `-full.webp`. `darken()` makes the three `-dark` copies (`floor.dark`): grey pixels get their lightness flipped between `dark.floor` and `dark.wall` (with `greyGamma` so light-grey rooms stay dark), coloured pixels keep their colour (dark ones lifted to `minColourLightness`; for the muted plan they recede instead). The labels layer keeps its alpha. `outline_pins()` then gives the meeting-point pins (`find_pins` rects) a thin `dark.pinOutline` line behind them in the dark labels layer, only on their coloured pixels (not label text).
7. **Hidden arrows.** `hiddenArrows` in the config lists arrow *tips* per floor; `find_arrow` collects the stroked lines ending there. `page_without` then takes them out of a copy of the page's PDF drawing code before the label layer is rendered: it tries each stroke-only `q … Q` group (smallest first) and drops it only if exactly some of those arrows vanish with it. So whatever lies under an arrow (the org-fair box's see-through fill, its outline) stays intact. If that can't be done cleanly (Canva changed how it writes the PDF), the report says so and the old way is used: `footprint` turns the arrows into polygons → `floor.hiddenLabels`, masked in the viewer (which also cuts through what's under them). If an arrow moved in Canva the report says so and nothing is hidden.

Then: write `overlay.generated.json`, merge overrides (`merge`: `_`-prefixed keys are comments and are dropped), write `data/overlay.json`, review pictures, report, validate.

### Overrides

Format is in the README. Rules of thumb:
- Fix *data* in `import/overlay.overrides.json` (ids, names, shapes, enabling categories).
- Fix *how the PDF is read* in `scripts/import-config.json` (new colour, new label rule, ignore something). Prefer this when the same mistake would come back on every re-import.
- Record owner decisions in `_decisions` with a date.

---

## 3. The viewer (`app.js`)

### State and flow

One state object `S` (floor, category `cat`, `item`, view `{k, x, y}`, `allLabels`, `allFloors`, `here`, …). Everything goes through `render()`, which redraws highlights, masks, the floor tabs, chips and the bottom card, and updates the URL (`history.replaceState`; `?floor=&cat=` or `?item=`; `?here=` and `?outline=1` are kept). Entry points: `setFloor`, `selectCat`, `selectItem`, `tap`.

### SVG layers (bottom to top), all inside one transformed `<g>` (`vp`)

1. `bgLayer`: muted plan.
2. `greyLayer`: grey copy of the plan, faded in while anything is selected.
3. `fullLayer`: full-colour plan, `clip-path` = the selected shapes. Fetched lazily on first highlight.
4. `dimRect`: light veil with a hole (`#hole` mask) for the selection.
5. `hlLayer`: highlight tint. No outline unless `?outline=1` or the floor has no full-colour layer. Dark category colours (rooms) get a highlighter instead (`isDark` → `.lighten`): `--room-tint` with `mix-blend-mode: multiply` in light mode (floor turns pale blue, black lines stay black) and `screen` in dark mode (dark floor lifts, light lines stay light). Browsers without blend modes get the old white veil (`--lighten`), which washes lines out.
6. `labelGreyLayer` (mask `#labg`) + `labelLayer` (mask `#lab`): the Canva layer twice. While selecting, the grey copy shows everything faded and the colour copy shows only the selected items' `labelBoxes` / `labelsWhenSelected`. `chromeBoxes` (title, legend) are faded. `hiddenLabels` and other items' `labelsWhenSelected` are masked out. "Aa" (`allLabels`) shows the colour layer unmasked, exactly as printed.
7. `traceLayer`: the outline the card's round icon draws (`traceOutlines`), and a shorter one on selecting an item (`traceOutlines(items, true)`, `.trace.quick`: 0.6 s + 0.25 s + 0.35 s = `TRACE_QUICK_MS`; only for items with a shape, pins have their ripple; tapping on the map plays it without moving the view): each shape's polygon, or a circle around a pin, with `pathLength="1"` so the CSS dash animation (`.trace`: draw 1 s, stay 0.5 s, fade 0.5 s) goes round exactly once at any zoom. **Don't add `vector-effect: non-scaling-stroke` to it**: browsers then measure the dash on screen, so the outline stopped short when zoomed in and wrapped round when zoomed out (the "wobbly, never closes" bug, fixed 5 Nov). The line width is set in map units for the zoom it's moving to instead. Removed after `TRACE_MS`, or at once when the selection changes.
8. `markerLayer`: screen-space, outside `vp`, so markers keep their size. Markers are drawn only for the searched/tapped item or things with nothing printed, and never for a category with `marker: false` (meeting points: the printed pin is the marker; the ripple centres on the pin's box instead). If the pin lies in one of the item's `labelBoxes` (rooms: the pin is the middle of the printed name), the marker's tip goes to the top middle of that box (`markerSpot`), so it never covers the name. The ripple (`.pulse`) only plays for items without a shape; a highlighted room needs none. The "You are here" dot (`?here=<item id>`, for QR codes on signs) is drawn here too, at that item's pin; its text tag shows for `HERE_TAG_MS` after load and after returning to its floor, then only the dot (the tag would cover printed labels). `withHere()` adds it to `showItems` so a category jump keeps it in view.

**Grey copies are made in the browser** (`greyed()`: canvas → desaturate → blob URL) once per floor, during idle time, so there is nothing extra to download. Until they're ready the old fading is used. Images created before they've loaded are kept hidden (an earlier bug showed one floor's grey copy on another floor).

### Masks are luminance

White = shown, black = hidden, grey = partly. Order of drawing inside `renderLabelMask` matters: base → chrome → selection in white → things to hide in black. Hidden things are drawn *after* the selection so a selected label box can't reveal a hidden arrow passing through it.

### View / gestures

- Pointer events for pan and pinch, wheel zoom, double-tap zoom. `clampView` keeps at least 60 px of the floor on screen; zoom is limited to 0.6–12 × `fitK`.
- `setView` animates; `shiftView` adjusts a running animation when the map area resizes (the search panel opening). Otherwise the ResizeObserver would cancel the jump.
- The bottom **card floats over the map** (`position: absolute`). The map must not change size when it opens, or the map visibly shifts. `--sheet-h` lifts the zoom button. `freeBox()` is the part of the map not covered by the card or the Aa button. Use it for anything that must "be visible": `centreOn`, `showItems`, `countVisible`.
- `centreOn(it)` (selecting an item, its round icon): zoom to at least 2.2 × `fitK`, but never so far that the item's outline doesn't fit the free box; rooms are centred on their outline, pins on the pin. (Before 5 Nov it centred on the pin at 2.2 ×, which made the Arnheim-Foyer look like a small room.)
- First-time hint on the card's round icon (`.dot-btn.hint`): three soft rings, `HINT_MS` per selection, until it has been tapped once (`localStorage['venueMap.dotSeen']`). The card is redrawn now and then; `--hint-delay` (negative mid-hint) lets the rings carry on instead of restarting or stopping.
- `showItems(items)`: keep the zoom if they fit, otherwise zoom out just enough, then pan the least. Used by the card's round icon, and automatically when a category is selected and none of its items are on screen.

### Tap hit-testing (`tap`)

Pins within 22 px, then printed labels (`labelBoxes` up to 4000 pt²; a label shared by several items of one category selects the category, e.g. the Org fair title), then the smallest shape containing the point.

### How to get here

- `S.cameFrom` = the floor you were on when `selectItem` switched floors (cleared by tapping a floor tab). The "from" floor is the `?here=` dot's floor if there is one, else `cameFrom`.
- `wayFrom(from, to)`: lifts and stairs on `from` whose `connects` include `to`. No direct stairs: the stairs that get closest in the right direction, and `via` = the floor to change at. With a here-dot on `from`: only the nearest of each.
- `S.way` is a third selection mode next to `item` and `cat` (render: `item` > `way` > `cat`); it ends when you leave its floor. Not in the URL.
- `connects` comes from the import (lift digits and "To floor …" notes, step 5); 2nd-floor stairs are overrides (their labels are hidden text), matched by position with the floors above and below. Stairs without `connects` are never suggested.

### Colours (light / dark)

- `<html data-theme>` = `light` / `dark`, or absent for automatic. An inline line in `index.html` sets it from `localStorage['venueMap.theme']` before anything draws; the round button (`#themeBtn`, under Aa) cycles auto → light → dark.
- `pic(f, key)` picks `f.dark[key]` while the page is dark. `applyMapTheme()` (button or the phone's own setting changing) swaps the `href` of every floor picture already made and rebuilds the grey copies; `greyGen` drops copies of the old theme still being made.
- CSS: `--map-bg` = `dark.floor` (so the map edge doesn't show), `--room-tint` / `--room-blend` = room highlighter (pale blue × multiply light, blue-grey × screen dark), `--lighten` = fallback white veil without blend modes (0.45 light, 0.14 dark).

### Search

- `search()` normalises accents and case and matches tokens or a compact form ("mpc3") against name, item aliases, description, category label and category aliases. Ranking: name prefix > name contains > other, this floor first.
- An empty query lists rooms, or the selected category when **Only <category>** is ticked, grouped by floor with sticky headings in the floor colour.
- **All floors** is on by default; unticked it limits the list to the current floor.
- `scrollToFloor` resets `scrollTop` to 0 before measuring, because sticky headings report their *stuck* `offsetTop`. It runs on open (and again in a rAF, since some browsers restore the old scroll) and when the floor changes with the panel open.
- No auto-focus on touch devices: the keyboard would hide the list.

---

## 4. Decisions so far (and why)

- The base plan is **muted**, and the selection shows in **full colour**. Everything else turns **grey** (not darker) while selecting, with only a light veil. The owner wanted the venue layout to stay readable and the *colours* to recede.
- **No outline** around selected areas (owner preference after comparing). `?outline=1` exists for comparison.
- Org fair boxes only while Org fair is selected; only the middle arrow from the "Organisations Fair" title is ever shown.
- Lifts enabled; stages extracted but off; spiral stairs counted as stairs; grey-boxed areas are closed; hidden old text ignored; English only. Coat check, first aid etc. are searchable rooms, not categories.
- Hosting: GitHub Pages, repo public. Possibly Cloudflare Pages + private repo later. **Moving host changes the URL and breaks printed QR codes**; settle it (or use an own domain) before printing.
- "No X on this floor": red text on the card only. A centre-screen message was tried and judged too much. The "Switched to …" message for automatic floor changes stays.
- Floor colours (room list bars, tab hairline): ground red `#D7263D`, 1st grey `#8A8F98`, 2nd green `#2E9E4F`, 3rd black `#111111` (lightened in dark mode).
- 3 Nov: true dark map, made by the import (not a CSS filter, which shifts colours; not in the browser, which costs older phones time). Colours keep their hue so the map still matches the chips and the printed posters. Auto / Light / Dark button, because people may want a bright map in a sunny foyer while their phone is dark (or the other way round).
- No offline mode on purpose: a stale cached map is worse than a slow one.
- 3 Nov: everyday search words live in the overrides (`aliases` on categories and items), not in code. Meal times are the catering items' `description`. A start view zoomed to the building (`floor.view`) was considered and dropped: on a portrait phone the building already fills the width, the empty space is the title/legend above and below.
- 3 Nov: "How to get here" highlights lifts and stairs on the floor you come from rather than drawing a route: the plan has no walkable paths, and the stair/lift choice is what people actually get wrong.
- 3 Nov: the museum exhibition gets its own category chip (Canva PDF with its label to come).
- 5 Nov: room outlines re-done (owner: most were rough; door swings made them look like a workaround). Outlines follow the walls with square corners, door swings are part of the room, doorways are cut along the wall line. Hand-drawn outlines replaced by the tracer where possible (Arnheim-Foyer, Humboldt Hall, Edison, Voltaire, 3rd-floor Foyer), using dividers for the open areas. Humboldt Hall is now the hall inside its inner walls plus stage; the strip between it and the cafeteria (with the projection booth) belongs to neither.
- 5 Nov: selecting a room draws its outline briefly (shorter than the round icon's), and the view shows the whole room rather than zooming in on its marker. New users get a gentle ring on the round icon until they've tapped it once (owner request: an unobtrusive tutorial).
- 5 Nov: a selected room is shown with a highlighter (blend mode) instead of a white veil, so its walls and door lines keep their contrast.
- 5 Nov: hidden arrows are removed from the PDF drawing before rendering instead of masked in the viewer (owner: the mask cut light stripes through the Org fair box the arrows crossed). They no longer show with *All labels* either.
- 5 Nov: the Org fair box's hiding area no longer clips things touching the box (owner: the charging-station arrowhead was cut off).
- 5 Nov: no app marker on a selected meeting point (owner: it stood beside the printed pin, two pins for one spot). A category flag (`marker: false`) rather than a check in code, so Catering / Project fair (also printed pins) can follow with one line in the config. Dark mode: printed meeting-point pins get a white hairline, made by the import, because their pale needle disappeared on the dark floor.

## 5. Known gaps / ideas not done

- Every room has an outline except Outside Area 1:1s (no edge on the plan; the paved strip by Point D4 could be outlined if that's the area). Still hand-drawn in the overrides: Kleist Hall (its seat rows still break the tracer), Registration/Info Desk/Wardrobe, Main entrance, Spontaneous Conversation Area (a Canva box). Still to confirm on site: where Arnheim-Foyer ends near the entrance, that the registration/wardrobe room is the tan strip + grey room, that the 3rd-floor Foyer/Voltaire split is the pillar row, and whether Humboldt Hall should include the strip towards the cafeteria.
- Still to verify on site: charging station position, the long arrows to D3 and C5, the 2nd-floor lift's floor list ("Goes to floors 0, 1, 3" is an override).
- Some arrows (e.g. D3's long arrow) aren't linked to their item, so they stay faded when it's selected. Fix by adding a `labelBoxes` entry via overrides.
- Toilets in the Nap Rooms wing aren't coloured on the plan, so they aren't in Toilets.

## 6. Working on it

- **Windows:** the command is `python`, not `python3`. The scripts read/write files as UTF-8 explicitly (Windows would otherwise use cp1252 and garble `·` and `–`). Re-running the import on another machine/library version may re-encode `source/raster/*.png` and `import/review/*.jpg` with different bytes but the same picture; don't commit those if nothing else changed.
- **Local preview:** `python3 -m http.server 8000` in the repo root, open `http://localhost:8000/`. Hard-reload after changes (images and `app.js` are cached).
- **Check in a phone-sized browser:** Playwright (on this Windows PC: `pip install playwright`, then `chromium.launch(channel="msedge")` uses the installed Edge, no browser download) with `viewport: {width: 390, height: 780}`, `isMobile: true, hasTouch: true`. Screenshot `?floor=…&cat=…` and `?item=…` states. Also check dark mode (`colorScheme: 'dark'`).
- **Before committing:** `node --check app.js`; `python3 scripts/validate.py`; if the import changed, look at `import/review/*.jpg` and the report.
- **Data contract changes:** update `schema/overlay.schema.json`, `scripts/validate.py` (if it needs a cross-check), the README "Data contract" section, and this file. New fields must be optional; the viewer must work without them.
- **Never rename an item id** that may be printed in a QR code (`?item=…`).
- **Branches:** work happens on a feature branch and is fast-forwarded into `main` when the owner says so; `main` is what's live.
- **Owner context:** not a software engineer. Explain changes in plain words, number options, give copy-pasteable commands. Mobile-first: judge every UI change on a phone-sized screen first.
