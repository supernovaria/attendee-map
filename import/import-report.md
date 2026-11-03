# Import report

Generated 2026-11-03T22:33:38+01:00 from `source/attendee-map.pdf` by `scripts/import.py`. Review pictures (every item drawn on the plan, red outline = shape, dot = pin, label = item id): [Ground floor](review/0.jpg), [1st floor](review/1.jpg), [2nd floor](review/2.jpg), [3rd floor](review/3.jpg).

## What the PDF contains

- Text labels: real, selectable text. Used for rooms, meeting points, catering, fairs, charging.
- Pins and the Org fair boxes: vector shapes. Used directly.
- **The floor plan itself, including the coloured toilets / stairs / lifts / stages, is one embedded picture per floor**, not vector shapes (same in the PPTX). Those areas were therefore found by colour in the picture (see the colour key in `scripts/import-config.json`). Check the review pictures for these especially.
- Room outlines are a flood-fill of the white space around each room label. Rooms with open doorways or a label outside the room get a pin only.

## Counts per floor

| Floor | Food & snacks | Lift | Org fair areas | Project fair | Spiral stairs | Stage | Stairs | Toilets | meeting points | rooms | rooms with outline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Ground floor | 1 | 2 | 3 | 0 | 0 | 0 | 3 | 1 | 4 | 8 | 4 |
| 1st floor | 1 | 2 | 0 | 1 | 0 | 3 | 4 | 2 | 6 | 6 | 4 |
| 2nd floor | 0 | 1 | 0 | 0 | 1 | 1 | 2 | 2 | 3 | 5 | 3 |
| 3rd floor | 1 | 1 | 0 | 0 | 1 | 1 | 2 | 2 | 4 | 5 | 3 |

Generated items: 80. Published in `data/overlay.json`: 75.

## Things to check (numbered so you can answer by number)

1. **Ground floor**: Meeting point D3: label is 198 pt from its pin (joined by an arrow?). Paired anyway - check.
2. **Ground floor**: Meeting point D3: another label is almost as close to its pin - check the pin is the right one.
3. **Ground floor**: "Charging Station": placed at arrow tip. Check the position on site.
4. **Ground floor**: Lift at (738, 380) is painted over by a box in Canva - left out. Is it closed/not for attendees?
5. **Ground floor**: Colour #846C0C covers ~221 pt² but is not in the colour key.
6. **Ground floor**: Prayer Room: label is outside the building; followed its lines to 1 room(s). Check on the review picture.
7. **Ground floor**: Parents Room: label is outside the building; followed its lines to 1 room(s). Check on the review picture.
8. **Ground floor**: Nap Rooms: label is outside the building; followed its lines to 4 room(s). Check on the review picture.
9. **Ground floor**: Rooms without an outline (pin only, at the label): Arnheim-Foyer (open area, no closed outline (58401 pt²)); Outside Area 1:1s (label is outside the building; no lines to follow); Registration / Info Desk / Wardrobe (no open floor right at the label (label outside the room?)); Main entrance (label is outside the building; no lines to follow)
10. **1st floor**: Meeting point C4: another label is almost as close to its pin - check the pin is the right one.
11. **1st floor**: Meeting point C5: label is 85 pt from its pin (joined by an arrow?). Paired anyway - check.
12. **1st floor**: Stairs at (762, 296) is painted over by a box in Canva - left out. Is it closed/not for attendees?
13. **1st floor**: Rooms without an outline (pin only, at the label): Kleist Hall (outline found was smaller than the label (furniture/seats in the way?)); Humboldt Hall (open area, no closed outline (61743 pt²))
14. **2nd floor**: Hidden text under the floor-plan picture was ignored (old labels left in Canva behind the image?): "Austen Kids Room"; "Networking 1:1s Spontaneous Conversation area"; "0, 1, 3"; "To floors 1 & 3"; "Point 3 - Conversation Area"; "Second Floor Foyer"; "To floor 3"; "Edison Workshops / Meet-ups"; "Darwin Speaker Room"; "Newton Office Hours"
15. **2nd floor**: Lift at (635, 537) is painted over by a box in Canva - left out. Is it closed/not for attendees?
16. **2nd floor**: Rooms without an outline (pin only, at the label): Spontaneous Conversation Area (open area, no closed outline (62070 pt²)); Edison (open area, no closed outline (69885 pt²))
17. **3rd floor**: Lift at (640, 534) is painted over by a box in Canva - left out. Is it closed/not for attendees?
18. **3rd floor**: Rooms without an outline (pin only, at the label): Third Floor Foyer (open area, no closed outline (127514 pt²)); Voltaire (open area, no closed outline (127514 pt²))
19. **all**: Near-duplicate shade: #84CC3D (drawn in Canva) is close to the Elevators colour but not the same. If it means the same thing, use the exact colour; if not, consider a more distinct one.
20. **overrides**: Not published (category switched off): stages

## How to fix things

Edit `import/overlay.overrides.json` (never `data/overlay.json` directly), then re-run `python3 scripts/import.py`. See the README section *Correcting the map*.
