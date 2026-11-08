# Import report

Generated 2026-11-08T13:12:02+01:00 from `source/attendee-map.pdf` by `scripts/import.py`. Review pictures (every item drawn on the plan, red outline = shape, dot = pin, label = item id): [Ground floor](review/0.jpg), [1st floor](review/1.jpg), [2nd floor](review/2.jpg), [3rd floor](review/3.jpg).

## What the PDF contains

- Text labels: real, selectable text. Used for rooms, meeting points, catering, fairs, charging.
- Pins and the Org fair boxes: vector shapes. Used directly.
- **The floor plan itself, including the coloured toilets / stairs / lifts / stages, is one embedded picture per floor**, not vector shapes (same in the PPTX). Those areas were therefore found by colour in the picture (see the colour key in `scripts/import-config.json`). Check the review pictures for these especially.
- Room outlines are traced from the plan around each room label: squares are fitted between the walls (so corners stay square and doorways are cut along the wall line), door swings count as room. Open areas without a wall between rooms need a divider in `scripts/import-config.json` (`roomShapes.dividers`); without one they get a pin only.

## Counts per floor

| Floor | Extras boxes | Fairs & booths boxes | Fairs & booths pins | Food & snacks boxes | Lift | Spiral stairs | Stage | Stairs | Toilets | meeting points | rooms | rooms with outline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ground floor | 3 | 3 | 0 | 1 | 2 | 0 | 0 | 3 | 1 | 4 | 8 | 5 |
| 1st floor | 0 | 1 | 1 | 1 | 2 | 0 | 3 | 4 | 2 | 6 | 6 | 6 |
| 2nd floor | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 2 | 2 | 3 | 5 | 5 |
| 3rd floor | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 2 | 2 | 4 | 5 | 5 |

Generated items: 80. Published in `data/overlay.json`: 75.

## Things to check (numbered so you can answer by number)

1. **Ground floor**: Prayer Room: label is outside the building; followed its lines to 1 room(s). Check on the review picture.
2. **Ground floor**: Parents Room: label is outside the building; followed its lines to 1 room(s). Check on the review picture.
3. **Ground floor**: Nap Rooms: label is outside the building; followed its lines to 3 room(s). Check on the review picture.
4. **Ground floor**: Rooms without an outline (pin only, at the label): Outside Area 1:1s (label is outside the building; no lines to follow); Registration / Info Desk / Wardrobe (outline found was smaller than the label (furniture/seats in the way?)); Main entrance (label is outside the building; no lines to follow)

## Already decided (acknowledged in `scripts/import-config.json`)

- **Ground floor**: Lift at (790, 381) is painted over by a box in Canva - left out. Is it closed/not for attendees? *(2 Nov 2026: areas painted over with grey boxes are closed off)*
- **Ground floor**: Colour #846C0C covers ~218 pt² but is not in the colour key. *(dark-yellow stair edge on the ground floor)*
- **1st floor**: Meeting point C4: another label is almost as close to its pin - check the pin is the right one. *(checked 8 Nov 2026 on the review picture: C4 is the pin beside the Kleist Hall label, C6 the one its arrow points at)*
- **1st floor**: Stairs at (762, 296) is painted over by a box in Canva - left out. Is it closed/not for attendees? *(2 Nov 2026: areas painted over with grey boxes are closed off)*
- **2nd floor**: Hidden text under the floor-plan picture was ignored (old labels left in Canva behind the image?): "Austen Kids Room"; "Networking 1:1s Spontaneous Conversation area"; "0, 1, 3"; "To floors 1 & 3"; "Point 3 - Conversation Area"; "Second Floor Foyer"; "To floor 3"; "Edison Workshops / Meet-ups"; "Darwin Speaker Room"; "Newton Office Hours" *(2 Nov 2026: hidden old text on the 2nd floor is stale)*
- **2nd floor**: Lift at (635, 537) is painted over by a box in Canva - left out. Is it closed/not for attendees? *(2 Nov 2026: areas painted over with grey boxes are closed off)*
- **3rd floor**: Lift at (640, 534) is painted over by a box in Canva - left out. Is it closed/not for attendees? *(2 Nov 2026: areas painted over with grey boxes are closed off)*
- **all**: Near-duplicate shade: #84CC3D (drawn in Canva) is close to the Elevators colour but not the same. If it means the same thing, use the exact colour; if not, consider a more distinct one. *(green Spontaneous Conversation Area box: a room, not a lift)*
- **all**: Near-duplicate shade: #FF822D (drawn in Canva) is close to the Stairs colour but not the same. If it means the same thing, use the exact colour; if not, consider a more distinct one. *(orange lightning of the charging label: the Charging colour, not stairs)*
- **overrides**: Not published (category switched off): stages *(stages extracted but not shown (decided 2 Nov 2026))*

## How to fix things

Edit `import/overlay.overrides.json` (never `data/overlay.json` directly), then re-run `python3 scripts/import.py`. See the README section *Correcting the map*.
