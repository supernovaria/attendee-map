#!/usr/bin/env python3
"""Import the Canva floor-plan PDF into the attendee map.

Run from the repository root:

    python3 scripts/import.py

What it does (see README "How the import works"):
  1. Renders one background picture per floor  -> maps/<floor>.webp
     and a high-res PNG per floor               -> source/raster/<floor>.png
  2. Reads the visible text labels, the pins drawn in Canva and the outlined
     boxes (vector data in the PDF).
  3. Finds the coloured areas (toilets, stairs, lifts, stages) by colour in the
     floor-plan picture, because the PDF has no vector shapes for them.
  4. Writes import/overlay.generated.json, import/import-report.md and
     review pictures in import/review/.
  5. Merges import/overlay.overrides.json (hand corrections) on top and writes
     data/overlay.json, then runs scripts/validate.py.

Re-running never touches import/overlay.overrides.json.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "scripts/import-config.json").read_text())
OUT_GEN = ROOT / "import/overlay.generated.json"
OUT_OVR = ROOT / "import/overlay.overrides.json"
OUT_REPORT = ROOT / "import/import-report.md"
OUT_FINAL = ROOT / "data/overlay.json"
REVIEW_DIR = ROOT / "import/review"
MAPS_DIR = ROOT / "maps"
RASTER_DIR = ROOT / "source/raster"

issues: list[tuple[str, str]] = []  # (floor name, text)


def issue(floor: str, text: str) -> None:
    issues.append((floor, text))


# ---------------------------------------------------------------- helpers
def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def r1(v: float) -> float:
    return round(float(v), 1)


def colour_close(a, b, tol=0.03) -> bool:
    return a is not None and all(abs(x - y) <= tol for x, y in zip(a, b))


def rect_dist(px, py, r) -> float:
    """Distance from point to rectangle (0 if inside)."""
    dx = max(r[0] - px, 0, px - r[2])
    dy = max(r[1] - py, 0, py - r[3])
    return math.hypot(dx, dy)


def in_box(x, y, box) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def greedy_match(points, blocks, max_dist):
    """Pair points with label blocks, closest pairs first. Returns
    (pairs[(pi, bi, dist)], unmatched point idx, unmatched block idx, ambiguous pi)."""
    cand = sorted(
        (rect_dist(p[0], p[1], b["bbox"]), pi, bi)
        for pi, p in enumerate(points)
        for bi, b in enumerate(blocks)
    )
    used_p, used_b, pairs = set(), set(), []
    for d, pi, bi in cand:
        if d > max_dist or pi in used_p or bi in used_b:
            continue
        pairs.append((pi, bi, d))
        used_p.add(pi)
        used_b.add(bi)
    ambiguous = set()
    for pi, bi, d in pairs:
        others = [rect_dist(points[pi][0], points[pi][1], b["bbox"]) for j, b in enumerate(blocks) if j != bi]
        if others and min(others) < max(d * 1.5, d + 12):
            ambiguous.add(pi)
    return (
        pairs,
        [i for i in range(len(points)) if i not in used_p],
        [i for i in range(len(blocks)) if i not in used_b],
        ambiguous,
    )


# ---------------------------------------------------------------- PDF reading
def covering_images(page):
    """Opaque images in draw order: (seqno, bbox). Things drawn before them
    and under them are invisible."""
    out = []
    for seq, (kind, r) in enumerate(page.get_bboxlog()):
        if kind == "fill-image":
            rr = pymupdf.Rect(r)
            if rr.width * rr.height > 0.25 * page.rect.width * page.rect.height:
                out.append((seq, rr))
    return out


def is_hidden(seqno, bbox, covers) -> bool:
    b = pymupdf.Rect(bbox)
    return any(seqno < cs and cr.contains(b) for cs, cr in covers)


def visible_lines(page, covers):
    trace = page.get_texttrace()
    lines, hidden = [], []
    for blk in page.get_text("dict")["blocks"]:
        if blk["type"] != 0:
            continue
        for ln in blk["lines"]:
            text = "".join(s["text"] for s in ln["spans"])
            text = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", text).strip()
            if not re.search(r"\w", text):
                continue
            lb = pymupdf.Rect(ln["bbox"])
            seqs = []
            for t in trace:
                tb = pymupdf.Rect(t["bbox"])
                inter = tb & lb
                if not inter.is_empty and inter.width * inter.height > 0.7 * max(tb.width * tb.height, 1e-6):
                    seqs.append(t["seqno"])
            seq = max(seqs) if seqs else 10**9
            entry = {
                "text": text,
                "bbox": tuple(lb),
                "size": ln["spans"][0]["size"],
                "rotated": abs(ln["dir"][1]) > 0.05,
            }
            (hidden if is_hidden(seq, lb, covers) else lines).append(entry)
    return lines, hidden


def group_blocks(lines):
    """Merge stacked lines (same label) into blocks."""
    lines = sorted(lines, key=lambda l: (l["bbox"][1], l["bbox"][0]))
    blocks = []
    for ln in lines:
        x0, y0, x1, y1 = ln["bbox"]
        cx = (x0 + x1) / 2
        target = None
        if not ln["rotated"]:
            for b in blocks:
                if b["rotated"]:
                    continue
                last = b["lines"][-1]
                lx0, ly0, lx1, ly1 = last["bbox"]
                gap = y0 - ly1
                if -2 <= gap < 6 and abs(cx - (lx0 + lx1) / 2) < max(x1 - x0, lx1 - lx0) / 2 + 6:
                    target = b
                    break
        if target:
            target["lines"].append(ln)
            bb = target["bbox"]
            target["bbox"] = (min(bb[0], x0), min(bb[1], y0), max(bb[2], x1), max(bb[3], y1))
        else:
            blocks.append({"lines": [ln], "bbox": ln["bbox"], "rotated": ln["rotated"]})
    for b in blocks:
        big = max(l["size"] for l in b["lines"])
        # name = leading lines at the biggest size; the rest is a description
        n = 0
        while n < len(b["lines"]) and b["lines"][n]["size"] >= big - 0.5:
            n += 1
        n = max(n, 1)
        b["name"] = " ".join(l["text"] for l in b["lines"][:n])
        b["desc"] = " ".join(l["text"] for l in b["lines"][n:])
        b["text"] = " ".join(l["text"] for l in b["lines"])
        b["cx"] = (b["bbox"][0] + b["bbox"][2]) / 2
        b["cy"] = (b["bbox"][1] + b["bbox"][3]) / 2
    return blocks


def cluster_drawings(drs):
    """Group drawings whose boxes touch into glyphs."""
    glyphs = []
    for d in drs:
        r = pymupdf.Rect(d["rect"])
        hit = None
        for g in glyphs:
            if (g["rect"] + (-2, -2, 2, 2)).intersects(r):
                hit = g
                break
        if hit:
            hit["rect"] |= r
            hit["parts"].append(d)
        else:
            glyphs.append({"rect": pymupdf.Rect(r), "parts": [d]})
    return glyphs


def find_pins(page, covers, fill, legend):
    drs = [
        d for d in page.get_drawings()
        if colour_close(d.get("fill"), fill)
        and not is_hidden(d.get("seqno", 10**9), d["rect"], covers)
    ]
    glyphs = [g for g in cluster_drawings(drs) if not in_box(g["rect"].x0, g["rect"].y0, legend)]
    needles = [d for d in page.get_drawings() if colour_close(d.get("fill"), (0.718, 0.788, 0.976))]
    pins = []
    for g in glyphs:
        r = g["rect"]
        needle = next((n for n in needles if (r + (-3, -3, 3, 3)).contains(pymupdf.Rect(n["rect"]))), None)
        if needle:  # meeting-point pin: needle points down-left
            tip = (needle["rect"].x0 + 1.5, needle["rect"].y1 - 1.5)
        else:  # navy pin: needle is the lowest part
            low = max(g["parts"], key=lambda d: d["rect"].y1)
            tip = ((low["rect"].x0 + low["rect"].x1) / 2, low["rect"].y1 - 1)
        pins.append({"tip": tip, "rect": tuple(r)})
    return pins


def canva_covers(page, covers):
    """Solid shapes drawn in Canva on top of the plan picture (e.g. grey boxes
    hiding a staircase). Returns list of Rects."""
    if not covers:
        return []
    img_seq = covers[0][0]
    out = []
    for d in page.get_drawings():
        f = d.get("fill")
        if f is None or d.get("seqno", 0) < img_seq or (d.get("fill_opacity") or 1) < 0.9:
            continue
        if max(f) < 0.05:  # pure black fills here are clipping artefacts
            continue
        r = d["rect"]
        if r.width * r.height >= 40:
            out.append(pymupdf.Rect(r))
    return out


def path_points(d):
    pts = []
    for it in d["items"]:
        if it[0] == "re":
            r = it[1]
            pts += [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
        elif it[0] == "qu":
            q = it[1]
            pts += [q.ul, q.ur, q.lr, q.ll]
        elif it[0] == "l":
            pts.append(it[1])
        elif it[0] == "c":
            pts.append(it[1])
    out = []
    for p in pts:
        p = (r1(p[0]), r1(p[1]))
        if not out or math.dist(out[-1], p) > 0.5:
            out.append(p)
    if len(out) > 2 and math.dist(out[0], out[-1]) < 0.5:
        out.pop()
    return out


def find_outlined_areas(page, covers, legend):
    """Unfilled boxes with a coloured outline (e.g. the Org fair areas)."""
    out = []
    for d in page.get_drawings():
        c = d.get("color")
        if d.get("fill") is not None or c is None:
            continue
        if max(c) - min(c) < 0.4:  # grey/black lines = arrows etc.
            continue
        r = d["rect"]
        if r.width * r.height < 600 or in_box(r.x0, r.y0, legend):
            continue
        if is_hidden(d.get("seqno", 10**9), r, covers):
            continue
        pts = path_points(d)
        if len(pts) >= 3:
            out.append({"points": [list(p) for p in pts], "rect": tuple(r), "color": c})
    return out


# ---------------------------------------------------------------- raster work
def render(page, scale):
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()


def contour_to_poly(cnt, scale, eps_pt=1.2):
    approx = cv2.approxPolyDP(cnt, eps_pt * scale, True)
    return [[r1(p[0][0] / scale), r1(p[0][1] / scale)] for p in approx]


def inside_point(mask, scale):
    """A point inside the mask near its centre (pt coords)."""
    ys, xs = np.nonzero(mask)
    cy, cx = ys.mean(), xs.mean()
    if mask[int(cy), int(cx)]:
        return [r1(cx / scale), r1(cy / scale)]
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
    y, x = np.unravel_index(np.argmax(dist), dist.shape)
    return [r1(x / scale), r1(y / scale)]


def colour_regions(img, rgb, tol, scale, min_area_pt2, exclude_boxes):
    diff = img.astype(np.int32) - np.array(rgb, np.int32)
    mask = (np.sqrt((diff ** 2).sum(2)) < tol).astype(np.uint8)
    for b in exclude_boxes:
        mask[int(b[1] * scale):int(b[3] * scale), int(b[0] * scale):int(b[2] * scale)] = 0
    k = max(3, int(4 * scale))  # close gaps from fixtures/text drawn on top (~4 pt)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    regions, small = [], 0
    for i in range(1, n):
        area_pt2 = stats[i, cv2.CC_STAT_AREA] / scale / scale
        if area_pt2 < min_area_pt2:
            small += 1
            continue
        m = (lab == i).astype(np.uint8)
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnt = max(cnts, key=cv2.contourArea)
        poly = contour_to_poly(cnt, scale)
        if len(poly) < 3:
            continue
        regions.append({"points": poly, "pin": inside_point(m, scale), "area": area_pt2})
    return regions, small


def plan_canvas(doc, page, scale):
    """The embedded floor-plan picture alone, placed where it sits on the page,
    at `scale` px per pt. White elsewhere. Text, pins and Canva boxes are not
    on it, so colour detection only sees the plan."""
    infos = sorted(page.get_image_info(xrefs=True), key=lambda i: -i["width"] * i["height"])
    info = infos[0]
    pix = pymupdf.Pixmap(doc, info["xref"])
    if pix.n - pix.alpha != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    src = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].copy()
    a, b, c, d, e, f = info["transform"]
    w, h = pix.width, pix.height
    M = np.float32([[scale * a / w, scale * c / h, scale * e], [scale * b / w, scale * d / h, scale * f]])
    W, H = int(page.rect.width * scale), int(page.rect.height * scale)
    return cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_AREA, borderValue=(255, 255, 255))


def room_shape(plan, seed_pt, scale, page_area_pt2):
    """Fill the white room around a label. Doorways are closed first by
    shrinking free space by DOOR pt, then the found room is grown back."""
    DOOR = 13  # closes openings up to ~26 pt wide (double doors)
    free = (plan.min(2) > 225).astype(np.uint8)
    r = int(DOOR * scale)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    core = cv2.erode(free, ker)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(core, 4)
    sx, sy = int(seed_pt[0] * scale), int(seed_pt[1] * scale)
    R = int(25 * scale)
    win = lab[max(0, sy - R):sy + R, max(0, sx - R):sx + R]
    ys, xs = np.nonzero(win)
    if not len(ys):
        return None, "no open floor right at the label (label outside the room?)"
    j = np.argmin((ys + max(0, sy - R) - sy) ** 2 + (xs + max(0, sx - R) - sx) ** 2)
    i = win[ys[j], xs[j]]
    x, y, w, h, _ = stats[i]
    Hh, Ww = lab.shape
    m = cv2.dilate((lab == i).astype(np.uint8), ker) & free
    area_pt2 = m.sum() / scale / scale
    if x <= r + 2 or y <= r + 2 or x + w >= Ww - r - 2 or y + h >= Hh - r - 2:
        return None, "label is outside the building"
    if area_pt2 > 0.05 * page_area_pt2:
        return None, f"open area, no closed outline ({area_pt2:.0f} pt²)"
    if area_pt2 < 300:
        return None, "area too small"
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contour_to_poly(max(cnts, key=cv2.contourArea), scale, 2.0), None


def unkeyed_colours(plan, scale, keys, exclude_boxes):
    """Saturated colours with real area that match no key/ignore entry."""
    a = plan.copy()
    for b in exclude_boxes:
        a[int(b[1] * scale):int(b[3] * scale), int(b[0] * scale):int(b[2] * scale)] = 255
    mx, mn = a.max(2).astype(int), a.min(2).astype(int)
    sat = (mx - mn) > 60
    px = a[sat].astype(int)
    if not len(px):
        return []
    near = np.zeros(len(px), bool)
    for k in keys:
        near |= np.sqrt(((px - np.array(k["rgb"])) ** 2).sum(1)) < k.get("tolerance", 48)
    rest = px[~near]
    if not len(rest):
        return []
    q = (rest // 24) * 24 + 12
    vals, counts = np.unique(q, axis=0, return_counts=True)
    out = []
    for v, c in sorted(zip(vals.tolist(), counts.tolist()), key=lambda t: -t[1]):
        area = c / scale / scale
        if area >= 120:
            out.append((tuple(v), area))
    return out[:8]


# ---------------------------------------------------------------- main
def main():
    MAPS_DIR.mkdir(exist_ok=True)
    RASTER_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(ROOT / CFG["pdf"])
    cats = {c["id"]: c for c in CFG["categories"]}
    legend = CFG["legendBox"]
    label_rules = [(re.compile(r["match"], re.I), r["category"]) for r in CFG["labelCategories"]]
    ignore_rules = [re.compile(p, re.I) for p in CFG["ignoreLabels"]]
    scale = CFG["rasterScale"]

    floors, items, raster_meta, stats = [], [], {}, {}
    used_ids: set[str] = set()

    def new_id(base: str) -> str:
        i, cand = 1, base
        while cand in used_ids:
            i += 1
            cand = f"{base}-{i}"
        used_ids.add(cand)
        return cand

    if len(doc) != len(CFG["floors"]):
        issue("all", f"PDF has {len(doc)} pages but config lists {len(CFG['floors'])} floors.")

    for fl in CFG["floors"]:
        page = doc[fl["page"]]
        fid, fname = fl["id"], fl["name"]
        W, H = page.rect.width, page.rect.height
        st = stats.setdefault(fname, {})
        exclude = [legend, [0, 0, W, CFG["titleMaxY"]]]

        # 1. backgrounds
        bscale = CFG["backgroundWidthPx"] / W
        bg = render(page, bscale)
        Image.fromarray(bg).save(MAPS_DIR / f"{fid}.webp", "WEBP", quality=72, method=6)
        img = render(page, scale)
        plan = plan_canvas(doc, page, scale)
        Image.fromarray(img).save(RASTER_DIR / f"{fid}.png", optimize=True)
        raster_meta[fid] = {
            "file": f"source/raster/{fid}.png",
            "widthPx": img.shape[1], "heightPx": img.shape[0],
            "pxPerUnit": scale, "floorWidth": r1(W), "floorHeight": r1(H),
        }
        floors.append({
            "id": fid, "name": fname, "shortName": fl.get("shortName", fname), "order": fl["order"],
            "background": f"maps/{fid}.webp", "width": r1(W), "height": r1(H),
        })

        # 2. vector data
        covers = covering_images(page)
        lines, hidden = visible_lines(page, covers)
        if hidden:
            hb = group_blocks(hidden)
            issue(fname, "Hidden text under the floor-plan picture was ignored (old labels left in Canva behind the image?): "
                  + "; ".join(f'"{b["text"]}"' for b in hb))
        blocks = [b for b in group_blocks(lines)
                  if not in_box(b["cx"], b["cy"], legend) and b["cy"] > CFG["titleMaxY"]]
        blocks = [b for b in blocks if not any(p.search(b["text"]) for p in ignore_rules)]

        point_blocks = [b for b in blocks if re.match(r"^point\b", b["text"], re.I)]
        cat_blocks, room_blocks = [], []
        for b in blocks:
            if b in point_blocks:
                continue
            cat = next((c for p, c in label_rules if p.search(b["text"])), None)
            if cat:
                b["category"] = cat
                cat_blocks.append(b)
            else:
                room_blocks.append(b)

        # 2a. meeting points
        mpins = find_pins(page, covers, CFG["markers"]["meetingPin"]["fill"], legend)
        pairs, up, ub, amb = greedy_match([p["tip"] for p in mpins], point_blocks, 220)
        for pi, bi, d in pairs:
            b = point_blocks[bi]
            m = re.match(r"^point\s+([A-Z]?\d+)\s*[-–]?\s*(.*)$", b["text"], re.I)
            code = m.group(1).upper() if m else b["text"]
            place = m.group(2).strip() if m else ""
            iid = new_id(f"mp-{slug(code)}")
            items.append({
                "id": iid, "floor": fid, "category": "meeting-points",
                "name": f"Meeting point {code}" + (f" · {place}" if place else ""),
                "aliases": [f"Point {code}", code, f"MP {code}", f"MP{code}"] + ([place] if place else []),
                "pin": [r1(mpins[pi]["tip"][0]), r1(mpins[pi]["tip"][1])],
            })
            if d > 60:
                issue(fname, f"Meeting point {code}: label is {d:.0f} pt from its pin (joined by an arrow?). Paired anyway - check.")
            if pi in amb:
                issue(fname, f"Meeting point {code}: another label is almost as close to its pin - check the pin is the right one.")
        for pi in up:
            t = mpins[pi]["tip"]
            issue(fname, f"Meeting-point pin at ({t[0]:.0f}, {t[1]:.0f}) has no 'Point …' label nearby - skipped.")
        for bi in ub:
            issue(fname, f'Label "{point_blocks[bi]["text"]}" has no pin nearby - skipped.')
        st["meeting points"] = len(pairs)

        # 2b. navy pins -> category from nearest label (Catering, Project fair)
        npins = find_pins(page, covers, CFG["markers"]["navyPin"]["fill"], legend)
        pin_label_blocks = [b for b in cat_blocks if b["category"] in ("food", "project-fair")]
        pairs, up, ub, amb = greedy_match([p["tip"] for p in npins], pin_label_blocks, 60)
        for pi, bi, d in pairs:
            b = pin_label_blocks[bi]
            b["used"] = True
            c = b["category"]
            iid = new_id(f"{c}-{fid}")
            near = nearest_room(b, room_blocks)
            items.append({
                "id": iid, "floor": fid, "category": c,
                "name": cats[c]["label"] if c != "food" else ("Catering" + (f" · {near}" if near else "")),
                "aliases": ["Catering", "Food", "Snacks", "Coffee"] if c == "food" else [b["text"]],
                "pin": [r1(npins[pi]["tip"][0]), r1(npins[pi]["tip"][1])],
            })
            st[cats[c]["label"]] = st.get(cats[c]["label"], 0) + 1
        for pi in up:
            t = npins[pi]["tip"]
            issue(fname, f"Dark-blue pin at ({t[0]:.0f}, {t[1]:.0f}) has no Catering/Project fair label - skipped.")

        # 2c. outlined areas -> nearest org/project fair label on the page
        fair_blocks = [b for b in cat_blocks if b["category"] in ("org-fair", "project-fair")]
        for n, area in enumerate(find_outlined_areas(page, covers, legend), 1):
            if not fair_blocks:
                issue(fname, f"Outlined box at {[round(v) for v in area['rect']]} has no fair label on this floor - skipped.")
                continue
            ax, ay = (area["rect"][0] + area["rect"][2]) / 2, (area["rect"][1] + area["rect"][3]) / 2
            b = min(fair_blocks, key=lambda b: rect_dist(ax, ay, b["bbox"]))
            b["used"] = True
            c = b["category"]
            pts = area["points"]
            items.append({
                "id": new_id(f"{c}-area-{fid}"), "floor": fid, "category": c,
                "name": cats[c]["label"] + " area",
                "aliases": [b["text"]],
                "shape": {"type": "polygon", "points": pts},
                "pin": [r1(ax), r1(ay)],
            })
            if len(fair_blocks) > 1:
                issue(fname, f"Outlined box at {[round(v) for v in area['rect']]} assigned to \"{b['text']}\" (nearest of several fair labels).")
            st[cats[c]["label"] + " areas"] = st.get(cats[c]["label"] + " areas", 0) + 1

        # 2d. charging + any unused category labels -> pin at label
        for b in cat_blocks:
            if b.get("used"):
                continue
            c = b["category"]
            if c in ("org-fair",):
                issue(fname, f'Label "{b["text"]}" has no outlined area - skipped.')
                continue
            pin = arrow_target(page, b) or [r1(b["cx"]), r1(b["cy"])]
            items.append({
                "id": new_id(f"{c}-{fid}"), "floor": fid, "category": c,
                "name": "Charging station" if c == "charging" else b["text"],
                "aliases": [b["text"]],
                "pin": pin,
            })
            how = "arrow tip" if pin != [r1(b["cx"]), r1(b["cy"])] else "the label (no pin found)"
            issue(fname, f'"{b["text"]}": placed at {how}. Check the position on site.')

        # 3. raster colour areas
        cover_rects = canva_covers(page, covers)
        for key in CFG["rasterKey"]:
            regs, small = colour_regions(plan, key["rgb"], key["tolerance"], scale, 40, exclude)
            regs.sort(key=lambda r: (r["pin"][1], r["pin"][0]))
            kept = []
            for reg in regs:
                xs = [p[0] for p in reg["points"]]
                ys = [p[1] for p in reg["points"]]
                rb = pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))
                hit = next((cr for cr in cover_rects
                            if (cr & rb).get_area() > 0.6 * max(rb.get_area(), 1e-6)), None)
                if hit:
                    issue(fname, f"{key['name']} at ({rb.x0:.0f}, {rb.y0:.0f}) is painted over by a box in Canva - left out. "
                          "Is it closed/not for attendees?")
                else:
                    kept.append(reg)
            regs = kept
            for reg in regs:
                c = key["category"]
                it = {
                    "id": new_id(f"{c}-{fid}"), "floor": fid, "category": c,
                    "name": key["name"],
                    "shape": {"type": "polygon", "points": reg["points"]},
                    "pin": reg["pin"],
                }
                if c == "lifts":
                    lab = lift_label(page, reg, lines)
                    if lab:
                        it["description"] = f"Goes to floors {lab}"
                items.append(it)
            st[key["name"]] = len(regs)
        for rgb, area in unkeyed_colours(plan, scale, CFG["rasterKey"] + CFG["ignoreRaster"], exclude):
            issue(fname, f"Colour #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X} covers ~{area:.0f} pt² but is not in the colour key.")

        # 4. rooms
        no_shape = []
        for b in room_blocks:
            name, desc = tidy_name(b)
            poly, why = room_shape(plan, (b["cx"], b["cy"]), scale, W * H)
            it = {
                "id": new_id(f"room-{slug(name)}"), "floor": fid, "category": "rooms",
                "name": name, "aliases": [],
                "pin": [r1(b["cx"]), r1(b["cy"])],
            }
            if desc:
                it["description"] = desc
            if poly:
                inside = cv2.pointPolygonTest(np.array(poly, np.float32), (float(b["cx"]), float(b["cy"])), True)
                lb = b["bbox"]
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                cov = max(0, min(lb[2], max(xs)) - max(lb[0], min(xs))) * max(0, min(lb[3], max(ys)) - max(lb[1], min(ys)))
                if inside < 0 or cov < 0.6 * (lb[2] - lb[0]) * (lb[3] - lb[1]):
                    poly, why = None, "outline found was smaller than the label (furniture/seats in the way?)"
            if poly:
                it["shape"] = {"type": "polygon", "points": poly}
            else:
                no_shape.append(f"{name} ({why})")
            items.append(it)
        st["rooms"] = len(room_blocks)
        st["rooms with outline"] = len(room_blocks) - len(no_shape)
        if no_shape:
            issue(fname, "Rooms without an outline (pin only, at the label): " + "; ".join(no_shape))

    # near-duplicate shades among vector fills vs key colours
    shade_check(doc, CFG)

    tz = dt.timezone(dt.timedelta(hours=1))  # CET; Nov = winter time
    generated = {
        "schemaVersion": 1,
        "updated": dt.datetime.now(tz).replace(microsecond=0).isoformat(),
        "source": "import:" + CFG["pdf"],
        "floors": floors,
        "categories": [{k: v for k, v in c.items()} for c in CFG["categories"]],
        "items": items,
    }
    OUT_GEN.parent.mkdir(exist_ok=True)
    OUT_GEN.write_text(json.dumps(generated, indent=1, ensure_ascii=False) + "\n")
    (RASTER_DIR / "rasters.json").write_text(json.dumps(raster_meta, indent=1) + "\n")

    final, merge_notes = merge(generated)
    OUT_FINAL.parent.mkdir(exist_ok=True)
    OUT_FINAL.write_text(json.dumps(final, indent=1, ensure_ascii=False) + "\n")
    for n in merge_notes:
        issue("overrides", n)

    draw_review(doc, generated, final)
    write_report(stats, generated, final)
    print(f"Wrote {OUT_FINAL.relative_to(ROOT)} ({len(final['items'])} items), report: {OUT_REPORT.relative_to(ROOT)}")
    sys.exit(subprocess.call([sys.executable, str(ROOT / "scripts/validate.py"), str(OUT_FINAL)]))


def nearest_room(b, rooms):
    if not rooms:
        return ""
    r = min(rooms, key=lambda r: math.hypot(r["cx"] - b["cx"], r["cy"] - b["cy"]))
    return tidy_name(r)[0] if math.hypot(r["cx"] - b["cx"], r["cy"] - b["cy"]) < 120 else ""


def tidy_name(b):
    name = re.sub(r"\s*-\s*-\s*", " / ", b["name"]).strip()
    return name, b["desc"].strip()


def lift_label(page, reg, lines):
    xs = [p[0] for p in reg["points"]]
    ys = [p[1] for p in reg["points"]]
    box = (min(xs) - 25, min(ys) - 25, max(xs) + 25, max(ys) + 25)
    for l in lines:
        if re.fullmatch(r"[0-9 ,&]+", l["text"]):
            cx, cy = (l["bbox"][0] + l["bbox"][2]) / 2, (l["bbox"][1] + l["bbox"][3]) / 2
            if in_box(cx, cy, box):
                return re.sub(r"\s*,\s*", ", ", l["text"].strip())
    return None


def arrow_target(page, b):
    """If a coloured arrow starts at this label, return the end far from it."""
    best = None
    for d in page.get_drawings():
        if d.get("fill") is None and d.get("color") is None:
            continue
        r = d["rect"]
        if r.width * r.height > 4000 or rect_dist((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2, b["bbox"]) > 45:
            continue
        for it in d["items"]:
            if it[0] != "l":
                continue
            for a, z in ((it[1], it[2]), (it[2], it[1])):
                if rect_dist(a.x, a.y, b["bbox"]) < 12 and rect_dist(z.x, z.y, b["bbox"]) > 25:
                    if not best or rect_dist(z.x, z.y, b["bbox"]) > best[0]:
                        best = (rect_dist(z.x, z.y, b["bbox"]), [r1(z.x), r1(z.y)])
    return best[1] if best else None


def shade_check(doc, cfg):
    fills = set()
    for page in doc:
        for d in page.get_drawings():
            f = d.get("fill")
            if f and max(f) - min(f) > 0.25:
                fills.add(tuple(round(v * 255) for v in f))
    for f in sorted(fills):
        for k in cfg["rasterKey"]:
            dist = math.dist(f, k["rgb"])
            if k["tolerance"] < dist < 90:
                issue("all", f"Near-duplicate shade: #{f[0]:02X}{f[1]:02X}{f[2]:02X} (drawn in Canva) is close to the {k['legend']} colour but not the same. "
                      "If it means the same thing, use the exact colour; if not, consider a more distinct one.")


# ---------------------------------------------------------------- overrides
def merge(gen):
    """generated + import/overlay.overrides.json -> final overlay."""
    ovr = json.loads(OUT_OVR.read_text()) if OUT_OVR.exists() else {}
    notes = []
    out = json.loads(json.dumps(gen))
    out.pop("source", None)
    out["source"] = "import"

    for fid, patch in (ovr.get("floors") or {}).items():
        f = next((f for f in out["floors"] if f["id"] == fid), None)
        if f is None:
            notes.append(f"Override for unknown floor '{fid}' ignored.")
        else:
            f.update({k: v for k, v in patch.items() if not k.startswith("_")})
    cat_ovr = ovr.get("categories") or {}
    for cid, patch in cat_ovr.items():
        patch = {k: v for k, v in patch.items() if not k.startswith("_")}
        c = next((c for c in out["categories"] if c["id"] == cid), None)
        if c is None:
            out["categories"].append({"id": cid, **patch})
        else:
            c.update(patch)
    if "categoryOrder" in ovr:
        order = {cid: i for i, cid in enumerate(ovr["categoryOrder"])}
        out["categories"].sort(key=lambda c: order.get(c["id"], 999))

    by_id = {it["id"]: it for it in out["items"]}
    for iid, patch in (ovr.get("items") or {}).items():
        if iid.startswith("_"):
            continue
        if iid not in by_id:
            notes.append(f"Override for item '{iid}' ignored: no such item in this import (was it renamed?).")
            continue
        if patch is None:
            out["items"].remove(by_id.pop(iid))
        else:
            for k, v in patch.items():
                if k.startswith("_"):
                    continue
                if v is None:
                    by_id[iid].pop(k, None)
                else:
                    by_id[iid][k] = v
    for it in ovr.get("add") or []:
        if it["id"] in by_id:
            notes.append(f"Added item '{it['id']}' replaces a generated item with the same id.")
            out["items"].remove(by_id[it["id"]])
        out["items"].append(it)

    enabled = {c["id"] for c in out["categories"] if c.get("enabled", True)}
    dropped = sorted({it["category"] for it in out["items"] if it["category"] not in enabled})
    out["items"] = [it for it in out["items"] if it["category"] in enabled]
    out["categories"] = [{k: v for k, v in c.items() if k != "enabled"} for c in out["categories"] if c["id"] in enabled]
    if dropped:
        notes.append("Not published (category switched off): " + ", ".join(dropped))
    if ovr.get("updated"):
        out["updated"] = ovr["updated"]
    return out, notes


# ---------------------------------------------------------------- review output
def draw_review(doc, gen, final):
    cats = {c["id"]: c for c in gen["categories"]}
    final_ids = {it["id"] for it in final["items"]}
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for fl in gen["floors"]:
        page = doc[next(f["page"] for f in CFG["floors"] if f["id"] == fl["id"])]
        s = 1.6
        base = Image.fromarray(render(page, s)).convert("RGBA")
        lay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        dr = ImageDraw.Draw(lay)
        for it in gen["items"]:
            if it["floor"] != fl["id"]:
                continue
            h = cats[it["category"]]["color"].lstrip("#")
            rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            off = it["id"] not in final_ids
            if "shape" in it:
                pts = [(x * s, y * s) for x, y in it["shape"]["points"]]
                dr.polygon(pts, fill=rgb + (50,), outline=(120, 120, 120, 255) if off else (220, 0, 60, 255), width=3)
            px, py = it["pin"][0] * s, it["pin"][1] * s
            dr.ellipse((px - 6, py - 6, px + 6, py + 6), fill=(220, 0, 60, 255), outline=(255, 255, 255, 255), width=2)
            dr.text((px + 8, py - 8), it["id"] + (" (off)" if off else ""), fill=(0, 0, 0, 255), font=font,
                    stroke_width=3, stroke_fill=(255, 255, 255, 255))
        Image.alpha_composite(base, lay).convert("RGB").save(REVIEW_DIR / f"{fl['id']}.jpg", quality=80)


def write_report(stats, gen, final):
    L = ["# Import report", "",
         f"Generated {gen['updated']} from `{CFG['pdf']}` by `scripts/import.py`. "
         "Review pictures (every item drawn on the plan, red outline = shape, dot = pin, label = item id): "
         + ", ".join(f"[{f['name']}](review/{f['id']}.jpg)" for f in gen["floors"]) + ".", "",
         "## What the PDF contains", "",
         "- Text labels: real, selectable text. Used for rooms, meeting points, catering, fairs, charging.",
         "- Pins and the Org fair boxes: vector shapes. Used directly.",
         "- **The floor plan itself, including the coloured toilets / stairs / lifts / stages, is one embedded picture per floor**, "
         "not vector shapes (same in the PPTX). Those areas were therefore found by colour in the picture (see the colour key in "
         "`scripts/import-config.json`). Check the review pictures for these especially.",
         "- Room outlines are a flood-fill of the white space around each room label. Rooms with open doorways or a label "
         "outside the room get a pin only.", "",
         "## Counts per floor", "",
         "| Floor | " + " | ".join(sorted({k for s in stats.values() for k in s})) + " |",
         "|---|" + "---|" * len({k for s in stats.values() for k in s})]
    keys = sorted({k for s in stats.values() for k in s})
    for f, s in stats.items():
        L.append(f"| {f} | " + " | ".join(str(s.get(k, 0)) for k in keys) + " |")
    L += ["", f"Generated items: {len(gen['items'])}. Published in `data/overlay.json`: {len(final['items'])}.", "",
          "## Things to check (numbered so you can answer by number)", ""]
    for n, (f, t) in enumerate(issues, 1):
        L.append(f"{n}. **{f}**: {t}")
    if not issues:
        L.append("Nothing flagged.")
    L += ["", "## How to fix things", "",
          "Edit `import/overlay.overrides.json` (never `data/overlay.json` directly), then re-run `python3 scripts/import.py`. "
          "See the README section *Correcting the map*.", ""]
    OUT_REPORT.write_text("\n".join(L))


if __name__ == "__main__":
    main()
