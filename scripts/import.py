#!/usr/bin/env python3
"""Import the Canva floor-plan PDF into the attendee map.

Run from the repository root:

    python3 scripts/import.py

What it does (see README "How the import works"):
  1. Renders one background picture per floor  -> maps/<floor>.webp
     (plus dark-mode copies                     -> maps/<floor>-dark.webp etc.)
     and a high-res PNG per floor               -> source/raster/<floor>.png
  2. Reads the visible text labels, the pins drawn in Canva and the outlined
     boxes (vector data in the PDF).
  3. Finds the coloured areas (toilets, stairs, lifts, stages) by colour in the
     floor-plan picture, because the PDF has no vector shapes for them.
  4. Writes import/overlay.generated.json, import/import-report.md and
     review pictures in import/review/.
  5. Merges import/overlay.overrides.json (hand corrections) on top and writes
     data/overlay.json and everything drawn in Canva as tagged vectors
     (maps/<floor>-labels.svg), then runs scripts/validate.py.

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
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "scripts/import-config.json").read_text(encoding="utf-8"))
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
        seqs = [d["seqno"] for d in g["parts"]] + ([needle["seqno"]] if needle else [])
        pins.append({"tip": tip, "rect": tuple(r), "seqs": seqs})
    return pins


def canva_covers(page, covers):
    """Solid grey/white boxes drawn in Canva on top of the plan picture (e.g.
    hiding a closed staircase) that are actually visible on the page.
    Returns list of (Rect, fill, [seqno, ...])."""
    if not covers:
        return []
    img_seq = covers[0][0]
    vs = 2
    page_px = render(page, vs).astype(int)
    out = []
    for d in page.get_drawings():
        f = d.get("fill")
        if f is None or d.get("seqno", 0) < img_seq or (d.get("fill_opacity") or 1) < 0.9:
            continue
        if max(f) < 0.05:  # pure black fills here are clipping artefacts
            continue
        if max(f) - min(f) > 0.05:  # coloured = pins, legend swatches, icons
            continue
        r = d["rect"]
        if r.width * r.height < 100:
            continue
        # skip boxes that do not show on the page (clipped away / covered)
        x0, y0, x1, y1 = [int(v * vs) for v in r]
        patch = page_px[max(0, y0):y1, max(0, x0):x1].reshape(-1, 3)
        if not len(patch) or (np.abs(patch - np.array(f) * 255).max(1) < 20).mean() < 0.3:
            continue
        same = next((o for o in out if pymupdf.Rect(r) == o[0] and tuple(f) == o[1]), None)
        if same:
            same[2].append(d["seqno"])
        else:
            out.append((pymupdf.Rect(r), tuple(f), [d["seqno"]]))
    return out


def plan_only_render(doc, page, s, C, boxes=(), clip=None):
    """The plan picture alone as it shows on the page (C = page render at the
    same scale), plus the Canva boxes that hide parts of it (they belong to
    the plan, so they get muted/dimmed with it). clip: the rectangle the page
    clips the picture to. Boxes are only painted where they show on the page
    (Canva clips some of them), copied from C."""
    info = max(page.get_image_info(xrefs=True), key=lambda i: i["width"] * i["height"])
    tmp = pymupdf.open()
    tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
    tp.insert_image(pymupdf.Rect(info["bbox"]), stream=doc.extract_image(info["xref"])["image"], keep_proportion=False)
    B = render(tp, s)
    if clip is not None:
        keep = np.zeros(B.shape[:2], bool)
        x0, y0, x1, y1 = [int(round(v * s)) for v in clip]
        keep[max(0, y0):y1, max(0, x0):x1] = True
        B[~keep] = 255
    for rect, fill, _ in boxes:
        x0, y0 = max(0, int(rect.x0 * s) - 1), max(0, int(rect.y0 * s) - 1)
        x1, y1 = int(math.ceil(rect.x1 * s)) + 1, int(math.ceil(rect.y1 * s)) + 1
        c = C[y0:y1, x0:x1]
        m = (np.abs(c.astype(int) - np.array(fill) * 255).max(2) < 30).astype(np.uint8)
        # text/pins drawn on the box: the box goes on under them (gaps up to ~3.5 pt)
        under = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((int(3.5 * s) | 1,) * 2, np.uint8)) > 0
        B[y0:y1, x0:x1][under] = np.round(np.array(fill) * 255).astype(np.uint8)
        m = cv2.dilate(m, np.ones((3, 3), np.uint8)) > 0  # and its soft edge, as on the page
        edge = m & ~under
        B[y0:y1, x0:x1][edge] = c[edge]
    return B


def mute(rgb):
    """Desaturate and lighten coloured pixels; greys (walls, outlines) untouched."""
    a = rgb.astype(np.float32) / 255
    grey = (a * np.array([0.299, 0.587, 0.114], np.float32)).sum(2, keepdims=True)
    sat = a.max(2, keepdims=True) - a.min(2, keepdims=True)
    k = np.clip(sat / 0.2, 0, 1)
    muted = (grey + (1 - grey) * 0.55) + (a - grey) * 0.22
    out = a * (1 - k) + muted * k
    return (out.clip(0, 1) * 255).astype(np.uint8)


def hexrgb(h):
    return np.array([int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


def darken(rgb, muted=False):
    """Dark-mode copy (settings: "dark" in the config). Greys get their
    lightness flipped (white floor -> dark, black walls/text -> light),
    coloured pixels keep their colour: dark ones (navy) are lifted so they
    stay readable; with `muted` they recede into the dark floor instead,
    like mute() does for the light plan."""
    d = CFG["dark"]
    floor, wall = hexrgb(d["floor"]), hexrgb(d["wall"])
    luma = np.array([0.299, 0.587, 0.114], np.float32)
    a = rgb.astype(np.float32) / 255
    y = (a * luma).sum(2, keepdims=True)
    k = np.clip((a.max(2, keepdims=True) - a.min(2, keepdims=True)) / 0.2, 0, 1)
    grey = floor + (1 - y) ** d["greyGamma"] * (wall - floor)
    col = a * d["colourKeep"]
    yc = (col * luma).sum(2, keepdims=True)
    if muted:
        col = yc * d["mutedLightness"] + (col - yc) * d["mutedSaturation"]
    else:
        col = col + np.maximum(0, d["minColourLightness"] - yc)
    out = grey * (1 - k) + col * k
    return (out.clip(0, 1) * 255).round().astype(np.uint8)


def leader_targets(C, B, scale, label_bbox, text_boxes):
    """Thin dark lines drawn in Canva (page render C darker than the plan
    alone B) that start at a label and point somewhere (e.g. "Nap Rooms"
    outside the building, with lines to each room). Returns
    [(end point, unit direction)] in pt. (Canva draws lines as clipped
    rectangles, so they're found in the picture, not in the vector data.)"""
    # darker than the plan underneath (also where a line crosses a grey wall)
    mask = (((B.astype(int) - C.astype(int)).max(2) > 20) & (C.max(2) < 120)).astype(np.uint8)
    for bb in text_boxes:  # text itself would look like short lines
        x0, y0, x1, y1 = [int(v * scale) for v in bb]
        mask[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2] = 0
    segs = cv2.HoughLinesP(mask * 255, 1, np.pi / 360, threshold=30,
                           minLineLength=int(20 * scale), maxLineGap=int(2 * scale))
    out = []
    for x1, y1, x2, y2 in ([] if segs is None else np.asarray(segs).reshape(-1, 4) / scale):
        d1, d2 = rect_dist(x1, y1, label_bbox), rect_dist(x2, y2, label_bbox)
        # one end at the label; rotated labels have big boxes, so the far end
        # may still be close to the box - require a long line instead
        if min(d1, d2) >= 10 or math.hypot(x2 - x1, y2 - y1) <= 20 or abs(d1 - d2) < 2:
            continue
        (nx, ny), (fx, fy) = ((x1, y1), (x2, y2)) if d1 < d2 else ((x2, y2), (x1, y1))
        L = math.hypot(fx - nx, fy - ny)
        out.append(((fx, fy), ((fx - nx) / L, (fy - ny) / L)))
    # one target per line: segments pointing the same way are the same line
    out.sort(key=lambda t: -rect_dist(t[0][0], t[0][1], label_bbox))
    uniq = []
    for t in out:
        if all(abs(t[1][0] * u[1][0] + t[1][1] * u[1][1]) < 0.9986 for u in uniq):  # > ~3°
            uniq.append(t)
    return uniq


def behind_wall(plan, scale, start, direction, max_pt=80):
    """Walk from `start` along `direction` until a wall has been crossed;
    return the first open-floor point behind it (where a leader line points)."""
    H, W = plan.shape[:2]
    crossed = False
    for i in range(int(max_pt * 2)):
        x = start[0] + direction[0] * i / 2
        y = start[1] + direction[1] * i / 2
        px, py = int(x * scale), int(y * scale)
        if not (0 <= px < W and 0 <= py < H):
            return None
        v = int(plan[py, px].min())
        if v < 140:
            crossed = True
        elif crossed and v > 225:
            return (x + direction[0] * 3, y + direction[1] * 3)
    return None


def xywh(r, pad=2.0):
    x0, y0, x1, y1 = r
    return [r1(x0 - pad), r1(y0 - pad), r1(x1 - x0 + 2 * pad), r1(y1 - y0 + 2 * pad)]


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


def find_arrow(page, tip, covers, reach=8):
    """Stroked line drawings (arrow shaft + head) with an end within `reach` pt of `tip`."""
    found = []
    for d in page.get_drawings():
        if d.get("fill") is not None or d.get("color") is None:
            continue
        segs = [(it[1], it[2]) for it in d["items"] if it[0] == "l"]
        if not segs or len(segs) != len(d["items"]):
            continue
        if is_hidden(d.get("seqno", 10**9), d["rect"], covers):
            continue
        if any(math.dist(q, tip) <= reach for a, b in segs for q in (a, b)):
            found.append(d)
    return found


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
            out.append({"points": [list(p) for p in pts], "rect": tuple(r), "color": c, "drawing": d})
    return out


# ---------------------------------------------------------------- vector label layer
# Everything Canva drew on top of the plan picture, as SVG (maps/<floor>-labels.svg).
# PyMuPDF writes the page as SVG with one element per drawing operation, in the
# same order as page.get_bboxlog() (checked below), so every element has a draw
# number (= the seqno of get_drawings / get_texttrace) and a box. That is how
# elements are left out (plan picture, things hidden behind it, Canva boxes
# painted into the plan, hiddenArrows) and tagged for the viewer.
SVG_NS, XLINK = "{http://www.w3.org/2000/svg}", "{http://www.w3.org/1999/xlink}"
NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def fnum(v, sig=5):
    """Short number for SVG: `sig` significant digits, no leading zero."""
    v = float(v)
    if abs(v) < 1e-6:
        return "0"
    s = f"{v:.{sig}g}"
    if "e" in s:
        s = f"{v:.{max(0, sig - 1 - int(math.floor(math.log10(abs(v)))))}f}"
        s = s.rstrip("0").rstrip(".") if "." in s else s
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s


def fpath(d):
    """Path data with short numbers (and a space wherever two numbers would merge)."""
    out, prev_num = [], False
    for tok in re.findall(r"[A-Za-z]|" + NUM.pattern, d):
        if tok.isalpha():
            out.append(tok)
            prev_num = False
        else:
            n = fnum(tok)
            if prev_num and not n.startswith("-"):
                out.append(" ")
            out.append(n)
            prev_num = True
    return "".join(out)


def svg_ops(page):
    """The page as PyMuPDF's SVG: (operations, elements by id). One operation
    per drawing operation: {el, chain (the <g> around it), seq, kind, bbox}."""
    root = ET.fromstring(page.get_svg_image(text_as_path=1))
    by_id = {e.get("id"): e for e in root.iter() if e.get("id")}
    ops = []

    def walk(e, chain):
        tag = e.tag.replace(SVG_NS, "")
        if tag in ("defs", "clipPath", "mask"):
            return
        if tag in ("path", "use", "image"):
            ops.append({"el": e, "chain": chain, "tag": tag})
            return
        for c in e:
            walk(c, chain + [e] if tag == "g" else chain)

    walk(root, [])
    log = page.get_bboxlog()
    kinds = {"use": "fill-text", "image": "fill-image"}
    if len(log) != len(ops) or any(
            kinds.get(o["tag"], "stroke-path" if o["el"].get("fill") == "none" else "fill-path") != k
            for o, (k, _) in zip(ops, log)):
        raise RuntimeError("PyMuPDF's SVG doesn't line up with the page's drawing log any more "
                           "(new PyMuPDF version?) - the label layer can't be made.")
    for i, (o, (k, r)) in enumerate(zip(ops, log)):
        o.update(seq=i, kind=k, bbox=pymupdf.Rect(r))
    return ops, by_id


def rect_box(e):
    """An axis-aligned clip rectangle "M x y H x V y H x Z" as a Rect, else None."""
    if len(e) != 1 or e[0].get("transform"):
        return None
    m = re.fullmatch(r"M(\S+?) ?(\S+)H(\S+)V(\S+)H(\S+)Z", e[0].get("d", "").replace(",", " "))
    if not m:
        return None
    try:
        x0, y0, x1, y1, x2 = map(float, m.groups())
    except ValueError:
        return None
    return pymupdf.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)) if abs(x2 - x0) < 1e-3 else None


def clip_of(page, seq):
    """The rectangle that drawing operation `seq` is clipped to (rectangular clips only)."""
    ops, by_id = svg_ops(page)
    out = pymupdf.Rect(page.rect)
    for g in ops[seq]["chain"]:
        m = re.fullmatch(r"url\(#([^)]+)\)", g.get("clip-path", ""))
        r = rect_box(by_id[m.group(1)]) if m and m.group(1) in by_id else None
        if r:
            out &= r
    return out


def overlap(a, b):
    """Share of box a (pymupdf.Rect, lines widened a little) that lies in b."""
    a = pymupdf.Rect(a) + (-0.5, -0.5, 0.5, 0.5)
    return (a & pymupdf.Rect(b)).get_area() / max(a.get_area(), 1e-6)


def box_rect(b):
    return pymupdf.Rect(b[0], b[1], b[0] + b[2], b[1] + b[3])


def label_layer(page, fid, plan_seq, covers, drop, sel, chrome, pins, items):
    """SVG text of the label layer for one floor.
    plan_seq: draw numbers of the plan picture; covers: covering_images();
    drop: draw numbers left out (Canva boxes painted into the plan, hidden arrows);
    sel: {draw number: item id} drawn only while that item is selected (Org fair boxes);
    chrome: [x, y, w, h] title/legend areas; pins: [[draw numbers]] of printed
    meeting-point pins (a white hairline round them in dark mode);
    items: the final items of this floor (their labelBoxes tag what belongs to them)."""
    ops, by_id = svg_ops(page)
    first_plan = min(plan_seq) if plan_seq else 0
    page_area = page.rect.width * page.rect.height
    keep = []
    for o in ops:
        s, bb = o["seq"], o["bbox"]
        if s in plan_seq or s in drop or is_hidden(s, bb, covers):
            continue
        if s < first_plan and bb.get_area() > 0.5 * page_area:
            continue  # white paper under the plan picture
        keep.append(o)

    # which item(s) each element belongs to
    boxes = [(it["id"], [box_rect(b) for b in it.get("labelBoxes", [])]) for it in items]
    chrome_r = [box_rect(b) for b in chrome]

    def tag(o):
        if o["seq"] in sel:
            return ("sel", sel[o["seq"]])
        if any(overlap(o["bbox"], c) >= 0.5 for c in chrome_r):
            return ("chrome", "")
        found = []  # (item id, area of the smallest of its boxes that holds the element)
        for iid, rs in boxes:
            inside = [r.get_area() for r in rs if overlap(o["bbox"], r) >= 0.5]
            joins = o["kind"] == "stroke-path" and sum(1 for r in rs if (o["bbox"] + (-1, -1, 1, 1)).intersects(r)) >= 2
            if inside or joins:  # inside its label/pin box, or a line joining two of its boxes
                found.append((iid, min(inside) if inside else 0))
        if o["kind"] != "fill-text" and len(found) > 1:
            # a drawn shape (arrow, pin) belongs to the item with the tightest box, not to a
            # big area box it happens to touch (the charging arrowhead at the Org fair box).
            # Text keeps all its items: a room name inside a fair box shows with either.
            least = min(a for _, a in found)
            found = [(i, a) for i, a in found if a <= 1.5 * least]
        return ("items", " ".join(sorted(i for i, _ in found)))

    # colours -> classes, so the viewer can grey them and dark mode can recolour them
    palette = {}

    def colour_class(prefix, col):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", col or ""):
            return None
        key = col.lower()
        palette.setdefault(key, len(palette))
        return f"{prefix}{palette[key]}"

    used = {}  # referenced defs: original id -> new id

    def ref(i):
        if i not in used:
            used[i] = f"f{fid}-{len(used)}"
            for v in by_id[i].iter():  # what the def itself refers to
                for a in v.attrib.values():
                    for j in re.findall(r"url\(#([^)]+)\)", a) + ([a[1:]] if a.startswith("#") else []):
                        if j in by_id:
                            ref(j)
        return used[i]

    def attrs(e, leaf=False, extra=None):
        out, cls = [], []
        items = list(e.attrib.items())
        if leaf and "fill" not in e.attrib:
            items.append(("fill", "#000000"))  # SVG's (and PDF's) default: black
        for k, v in items:
            k = k.replace(XLINK, "")
            if k.startswith("{") or k in ("id", "data-text"):
                continue
            if leaf and k in ("fill", "stroke") and v != "none":
                c = colour_class("f" if k == "fill" else "s", v)
                if c:
                    cls.append(c)
                    continue
            if k == "d":
                v = fpath(v)
            elif k in ("transform", "x", "y", "width", "height", "stroke-width", "stroke-miterlimit", "opacity",
                       "fill-opacity", "stroke-opacity", "stroke-dashoffset", "stroke-dasharray"):
                v = NUM.sub(lambda m: fnum(m.group()), v)
            elif k == "href" and v.startswith("data:"):
                v = re.sub(r"\s", "", v)
            elif k == "href" and v.startswith("#"):
                v = "#" + ref(v[1:])
            elif "url(#" in v:
                v = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{ref(m.group(1))})", v)
            out.append((k, v))
        out += list((extra or {}).items())
        if cls:
            out.append(("class", " ".join(cls)))
        return "".join(f' {k}="{html_attr(v)}"' for k, v in out)

    def needed(g, bb):
        """Is this <g> around an element doing anything? Clip rectangles that
        hold the whole element are left out (Canva nests seven of them)."""
        if set(g.attrib) - {"clip-path"}:
            return True
        m = re.fullmatch(r"url\(#([^)]+)\)", g.get("clip-path", ""))
        r = rect_box(by_id[m.group(1)]) if m and m.group(1) in by_id else None
        return not (r and (r + (-1, -1, 1, 1)).contains(bb))

    pin_of = {s: n for n, p in enumerate(pins) for s in p}
    pin_ops = {}
    for o in keep:
        if o["seq"] in pin_of:
            pin_ops.setdefault(pin_of[o["seq"]], []).append(o)
    halo_w = CFG["dark"].get("pinOutlinePt", 0)

    body, open_tag, open_chain = [], None, []

    def close_chain(n):
        while len(open_chain) > n:
            open_chain.pop()
            body.append("</g>")

    for o in keep:
        t = tag(o)
        chain = [g for g in o["chain"] if needed(g, o["bbox"])]
        if t != open_tag:
            close_chain(0)
            if open_tag is not None:
                body.append("</g>")
            kind, val = t
            body.append({"sel": f'<g data-sel="{val}">', "chrome": '<g class="chrome">',
                         "items": f'<g data-i="{val}">' if val else "<g>"}[kind])
            open_tag = t
        n = 0
        while n < len(open_chain) and n < len(chain) and open_chain[n] is chain[n]:
            n += 1
        close_chain(n)
        for g in chain[n:]:
            body.append(f"<g{attrs(g)}>")
            open_chain.append(g)
        p = pin_of.get(o["seq"])
        if p is not None and halo_w and pin_ops[p][0] is o:
            # dark mode: a hairline behind the whole pin, so its pale needle shows on the dark floor
            for q in pin_ops[p]:
                if q["tag"] != "path":
                    continue
                tr = q["el"].get("transform", "")
                m = [float(v) for v in NUM.findall(tr)] if tr.startswith("matrix") else [1, 0, 0, 1]
                k = math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) or 1
                tr = NUM.sub(lambda x: fnum(x.group()), tr)
                body.append('<path class="h"' + (f' transform="{tr}"' if tr else "")
                            + f' d="{fpath(q["el"].get("d", ""))}" stroke-width="{fnum(2 * halo_w / k)}" stroke-linejoin="round"/>')
        tagname = o["tag"]
        if tagname == "image":
            body.append(f"<image{attrs(o['el'])}/>")
        else:
            body.append(f"<{tagname}{attrs(o['el'], leaf=True)}/>")
    close_chain(0)
    if open_tag is not None:
        body.append("</g>")

    # defs (in the order they first appear in PyMuPDF's file, so re-runs give the same file)
    order = {e.get("id"): n for n, e in enumerate(by_id.values())}

    def ser(e):
        tag = e.tag.replace(SVG_NS, "")
        a = attrs(e)
        if e.get("id") in used:
            a = f' id="{used[e.get("id")]}"' + a
        kids = "".join(ser(c) for c in e)
        return f"<{tag}{a}>{kids}</{tag}>" if kids else f"<{tag}{a}/>"

    defs, done = [], set()
    while len(done) < len(used):  # serialising can add references (masks -> images)
        for i in sorted(set(used) - done, key=lambda i: order[i]):
            done.add(i)
            defs.append((order[i], ser(by_id[i])))
    defs = "".join(d for _, d in sorted(defs))

    # colours: as printed, greyed (others while something is selected), and both for dark mode
    luma = np.array([0.299, 0.587, 0.114])
    hx = lambda a: "#" + "".join(f"{int(round(v)):02x}" for v in np.clip(a, 0, 255))
    css = [f".vl-{fid} .h{{fill:{CFG['dark'].get('pinOutline', '#ffffff')};stroke:{CFG['dark'].get('pinOutline', '#ffffff')}}}"]
    for col, n in palette.items():
        rgb = hexrgb(col) * 255
        drk = darken(np.array([[np.round(rgb)]], np.uint8))[0, 0].astype(float)
        for mode, c in (("", rgb), (".dark ", drk)):
            for state, v in (("", c), (".off ", np.full(3, (c * luma).sum()))):
                css.append(f"{mode}.vl-{fid} {state}.f{n}{{fill:{hx(v)}}}{mode}.vl-{fid} {state}.s{n}{{stroke:{hx(v)}}}")
    W, H = fnum(page.rect.width), fnum(page.rect.height)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">\n'
            f"<style>{''.join(css)}</style>\n<defs>{defs}</defs>\n"
            f'<g class="vl-{fid}">\n' + "\n".join(body) + "\n</g>\n</svg>\n")


def html_attr(v):
    return str(v).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


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


# ---------------------------------------------------------------- room outlines
def _disk(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def square_morph(mask, r, angle=0.0, op=cv2.MORPH_OPEN):
    """Opening (or closing) by a square of side 2r+1 turned by `angle` degrees.
    Opening keeps every part of `mask` such a square fits in: square corners
    stay square, openings narrower than the square are cut along the wall."""
    k = np.ones((2 * r + 1, 2 * r + 1), np.uint8)
    if abs(angle) < 1:
        return cv2.morphologyEx(mask, op, k)
    h, w = mask.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
    c, s = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * s + w * c) + 2, int(h * c + w * s) + 2
    M[0, 2] += nw / 2 - w / 2
    M[1, 2] += nh / 2 - h / 2
    rot = cv2.warpAffine(mask, M, (nw, nh), flags=cv2.INTER_NEAREST, borderValue=0)
    back = cv2.warpAffine(cv2.morphologyEx(rot, op, k), cv2.invertAffineTransform(M), (w, h),
                          flags=cv2.INTER_NEAREST, borderValue=0)
    return back & mask if op == cv2.MORPH_OPEN else back | mask


def wall_angles(walls, scale, n=2):
    """Up to n main directions of the straight wall edges in a wall mask
    (degrees, -45..45, 0 = upright), strongest first."""
    cnts, _ = cv2.findContours(walls.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    angs, lens = [], []
    for c in cnts:
        p = cv2.approxPolyDP(c, 1.0 * scale, True)[:, 0, :].astype(float)
        d = np.roll(p, -1, 0) - p
        L = np.hypot(d[:, 0], d[:, 1])
        k = L > 12 * scale
        angs += list(np.degrees(np.arctan2(d[k, 1], d[k, 0])) % 90)
        lens += list(L[k])
    angs, lens = np.array(angs), np.array(lens)
    out, top = [], 0
    while len(angs) and len(out) < n:
        h, _ = np.histogram(angs, bins=90, range=(0, 90), weights=lens)
        h = h + np.roll(h, 1) + np.roll(h, -1)
        best = int(np.argmax(h))
        if out and h[best] < 0.15 * top:
            break
        top = top or h[best]
        off = (angs - best - 0.5 + 45) % 90 - 45
        near = np.abs(off) < 2.5
        a = best + 0.5 + float((off[near] * lens[near]).sum() / lens[near].sum())
        a = a if a < 45 else a - 90
        out.append(0.0 if abs(a) < 1 else round(a, 1))
        angs, lens = angs[np.abs(off) >= 5], lens[np.abs(off) >= 5]
    return out or [0.0]


def nearest_label(lab, sx, sy, R):
    y0, x0 = max(0, sy - R), max(0, sx - R)
    win = lab[y0:sy + R, x0:sx + R]
    ys, xs = np.nonzero(win)
    if not len(ys):
        return 0
    j = np.argmin((ys + y0 - sy) ** 2 + (xs + x0 - sx) ** 2)
    return int(win[ys[j], xs[j]])


def grow_labels(lab, free, steps):
    """Let every labelled area claim the free pixels closest to it (up to `steps` px)."""
    lab = lab.astype(np.float32)
    k = np.ones((3, 3), np.uint8)
    for _ in range(steps):
        g = cv2.dilate(lab, k)
        new = (lab == 0) & (free > 0) & (g > 0)
        if not new.any():
            break
        lab[new] = g[new]
    return lab


def largest(mask):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=4)
    if n < 2:
        return mask.astype(np.uint8) * 0
    return (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)


def floor_masks(plan, scale, floor_rgb=(), thin_pt=2.0, door_pt=10, dark=170, dividers=()):
    """What the room finder needs from one plan picture:
    walls   - grey areas thicker than thin_pt, and long thin lines darker than
              `dark` (thin walls); light thin lines (door swings) are not walls,
    floorA  - floor with door leaves/arcs and window frames still closed
              (decides which room is which: doors keep rooms apart),
    floorB  - floor without any thin lines (decides the shape: door swings
              and seat rows inside a room belong to it),
    outside - white connected to the page edge.
    dividers (lists of [x, y] pt) are drawn in as walls: they split open areas
    the plan has no wall for (a folding partition, a row of pillars)."""
    nonwhite = plan.min(2) <= 225
    keep = np.zeros(nonwhite.shape, bool)  # coloured areas that count as floor (stages)
    for rgb, tol in floor_rgb:
        keep |= np.sqrt(((plan.astype(np.int32) - np.array(rgb)) ** 2).sum(2)) < tol
    t = max(1, int(round(thin_pt * scale / 2)))
    walls = cv2.morphologyEx((nonwhite & ~keep).astype(np.uint8), cv2.MORPH_OPEN, _disk(t)) > 0
    thin = (nonwhite & ~walls & ~keep).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(thin, connectivity=8)
    big = np.zeros(n, bool)
    big[1:] = np.maximum(st[1:, 2], st[1:, 3]) >= door_pt * scale  # door leaves, arcs, window frames
    doors = big[lab]
    near_keep = cv2.dilate(keep.astype(np.uint8), _disk(max(1, int(2 * scale)))) > 0
    doors &= ~near_keep  # the outline and tiles of a stage don't split a room
    thin_walls = doors & (plan.min(2) < dark)
    walls |= cv2.dilate(thin_walls.astype(np.uint8), np.ones((3, 3), np.uint8)) & nonwhite & ~keep > 0
    if dividers:
        drawn = np.zeros(walls.shape, np.uint8)
        for line in dividers:
            cv2.polylines(drawn, [(np.array(line) * scale).astype(np.int32)], False, 1, max(2, int(1.5 * scale)))
        walls |= drawn > 0
    n, lab = cv2.connectedComponents((~nonwhite).astype(np.uint8), connectivity=4)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    outside = cv2.dilate(np.isin(lab, edge[edge > 0]).astype(np.uint8), _disk(t + 1)) > 0
    return {"walls": walls, "outside": outside, "scale": scale,
            "floorA": (~walls & ~doors & ~outside).astype(np.uint8),
            "floorB": (~walls & ~outside).astype(np.uint8)}


def room_mask(P, seed_pt, door_pt=13, opening_pt=18, slot_pt=4, max_area_pt2=None, search_pt=25, skip_big=False):
    """The room around seed_pt as a mask (and its x/y offset), or (None, reason).

    1. Squares of side 2*door_pt are fitted into the floor (door leaves count
       as walls): each connected group of them is one room; doorways narrower
       than the square keep rooms apart.
    2. Each room then claims the floor nearest to it with thin lines ignored,
       so door swings and seat rows count as room.
    3. Anything narrower than 2*opening_pt sticking out of it (a doorway) is
       cut off along the wall line; slots narrower than 2*slot_pt (short wall
       stubs, pillars) are filled.
    Squares are turned to the walls around the room; for rooms between walls at
    two angles the results for both are combined.
    The room is the one nearest seed_pt within search_pt; with skip_big, rooms
    larger than max_area_pt2 are passed over instead of reported."""
    s = P["scale"]
    r = int(door_pt * s)
    sx, sy = int(seed_pt[0] * s), int(seed_pt[1] * s)
    if not skip_big and P["outside"][sy, sx]:
        return None, "label is outside the building"
    key = ("rooms", door_pt)
    if key not in P:
        P[key] = cv2.connectedComponentsWithStats(square_morph(P["floorA"], r), connectivity=4)
    _, lab0, st, _ = P[key]
    if skip_big and max_area_pt2:
        small = st[:, 4] / s / s <= max_area_pt2
        small[0] = False
        i = nearest_label(np.where(small[lab0], lab0, 0), sx, sy, int(search_pt * s))
    else:
        i = nearest_label(lab0, sx, sy, int(search_pt * s))
    if not i:
        return None, "no open floor right at the label (label outside the room?)"
    x, y, w, h, area = st[i]
    if max_area_pt2 and area / s / s > max_area_pt2:
        return None, f"open area, no closed outline ({area / s / s:.0f} pt²)"
    H, W = lab0.shape
    p = 3 * r
    x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
    crop = lambda a: a[y0:y1, x0:x1]
    near = cv2.dilate((crop(lab0) == i).astype(np.uint8), np.ones((r, r), np.uint8)) > 0
    angs = wall_angles(crop(P["walls"]) & near, s)
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    for ang in angs:
        A = square_morph(crop(P["floorA"]), r, ang)
        B = square_morph(crop(P["floorB"]), r, ang)
        _, lab = cv2.connectedComponents(A, connectivity=4)
        j = nearest_label(lab, sx - x0, sy - y0, int(search_pt * s))
        if not j:
            continue
        one = (grow_labels(lab, A | B, 3 * r) == j).astype(np.uint8)
        cut = square_morph(one, int(opening_pt * s), ang)
        m |= cut if cut.sum() > 0.7 * one.sum() else one
    if not m.any():
        return None, "no open floor right at the label (label outside the room?)"
    for ang in angs:
        m = square_morph(m, max(1, int(slot_pt * s)), ang, cv2.MORPH_CLOSE)
    m = largest(m & ~crop(P["outside"]))
    return (m, (x0, y0)), None


def mask_to_poly(m, off, scale, eps_pt=1.0):
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE, offset=off)
    c = max(cnts, key=cv2.contourArea)
    a = cv2.approxPolyDP(c, eps_pt * scale, True)
    return [[round(float(q[0][0]) / scale, 1), round(float(q[0][1]) / scale, 1)] for q in a]


def room_settings():
    rs = CFG.get("roomShapes", {})
    keys = {k["category"]: k for k in CFG["rasterKey"]}
    floor_rgb = [(keys[c]["rgb"], keys[c].get("tolerance", 48)) for c in rs.get("floorColours", []) if c in keys]
    return rs, floor_rgb


def room_shape(P, seed_pt, page_area_pt2, name=""):
    """Outline of the room around a label: (polygon, None) or (None, reason).
    roomShapes.perRoom[name] can change doorPt/openingPt for one room."""
    rs, _ = room_settings()
    own = rs.get("perRoom", {}).get(name, {})
    res, why = room_mask(P, seed_pt, own.get("doorPt", rs.get("doorPt", 13)), own.get("openingPt", rs.get("openingPt", 18)),
                         rs.get("slotPt", 4), max_area_pt2=rs.get("maxPageShare", 0.05) * page_area_pt2)
    if why:
        return None, why
    m, off = res
    if m.sum() / P["scale"] ** 2 < 300:
        return None, "area too small"
    return mask_to_poly(m, off, P["scale"], rs.get("simplifyPt", 1.0)), None


def room_near(P, pt, page_area_pt2, radius=15):
    """The indoor room closest to `pt` (e.g. where a leader line ends on a
    window), traced with small doorways (these rooms are small). Outdoor space
    and huge areas are skipped."""
    rs, _ = room_settings()
    door = rs.get("smallDoorPt", 5)
    res, why = room_mask(P, pt, door, rs.get("smallOpeningPt", 8), rs.get("slotPt", 4),
                         max_area_pt2=0.05 * page_area_pt2, search_pt=radius, skip_big=True)
    if why:
        return None
    m, off = res
    if m.sum() / P["scale"] ** 2 < 150:
        return None
    return mask_to_poly(m, off, P["scale"], rs.get("simplifyPt", 1.0))


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
    layers_todo = []
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
            **({"color": fl["color"]} if fl.get("color") else {}),
            "background": f"maps/{fid}.webp",
            "backgroundHighlight": f"maps/{fid}-full.webp",
            "labels": f"maps/{fid}-labels.svg",
            "dark": {
                "background": f"maps/{fid}-dark.webp",
                "backgroundHighlight": f"maps/{fid}-full-dark.webp",
            },
            "width": r1(W), "height": r1(H),
        })
        floor_rec = floors[-1]
        first_item = len(items)

        # 2. vector data
        covers = covering_images(page)
        sel = {}  # draw number -> item id: printed only while that item is selected
        # arrows switched off in the config (hiddenArrows: floor -> arrow tips):
        # left out of the label layer (step 6)
        arrows = []
        for tip in CFG.get("hiddenArrows", {}).get(fid, []):
            found = find_arrow(page, tip, covers)
            if found:
                arrows += found
            else:
                issue(fname, f"hiddenArrows: no arrow ends near {tip} any more (Canva layout changed?) - nothing hidden there.")
        lines, hidden = visible_lines(page, covers)
        if hidden:
            hb = group_blocks(hidden)
            issue(fname, "Hidden text under the floor-plan picture was ignored (old labels left in Canva behind the image?): "
                  + "; ".join(f'"{b["text"]}"' for b in hb))
        all_blocks = group_blocks(lines)
        chrome = [xywh(b["bbox"], 4) for b in all_blocks if b["cy"] <= CFG["titleMaxY"]]
        chrome.append(xywh(legend, 0))
        blocks = [b for b in all_blocks
                  if not in_box(b["cx"], b["cy"], legend) and b["cy"] > CFG["titleMaxY"]]
        notes = [b for b in blocks if any(p.search(b["text"]) for p in ignore_rules)]
        blocks = [b for b in blocks if b not in notes]

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
                "labelBoxes": [xywh(b["bbox"]), xywh(mpins[pi]["rect"])],
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
                "labelBoxes": [xywh(b["bbox"]), xywh(npins[pi]["rect"])],
            })
            st[cats[c]["label"]] = st.get(cats[c]["label"], 0) + 1
        for pi in up:
            t = npins[pi]["tip"]
            issue(fname, f"Dark-blue pin at ({t[0]:.0f}, {t[1]:.0f}) has no Catering/Project fair label - skipped.")

        # 2c. outlined areas -> nearest org/project fair label on the page
        fair_blocks = [b for b in cat_blocks if b["category"] in ("org-fair", "project-fair")]
        outlined = find_outlined_areas(page, covers, legend)
        for n, area in enumerate(outlined, 1):
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
                "labelBoxes": [xywh(area["rect"], 4), xywh(b["bbox"])],
            })
            if c in CFG.get("boxesOnlyWhenSelected", []):
                # the printed box (its outline and its see-through fill, which Canva
                # writes as a picture of the same size) is only shown while selected
                ar = pymupdf.Rect(area["rect"])
                for k, r in enumerate(page.get_bboxlog()):
                    rr = pymupdf.Rect(r[1])
                    if k == area["drawing"]["seqno"] or r[0] in ("fill-image", "fill-path") and                             max(abs(a - b) for a, b in zip(rr, ar)) < 3:
                        sel[k] = items[-1]["id"]
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
                "labelBoxes": [xywh((min(b["bbox"][0], pin[0]), min(b["bbox"][1], pin[1]),
                                     max(b["bbox"][2], pin[0]), max(b["bbox"][3], pin[1])), 12)],
            })
            how = "arrow tip" if pin != [r1(b["cx"]), r1(b["cy"])] else "the label (no pin found)"
            issue(fname, f'"{b["text"]}": placed at {how}. Check the position on site.')

        # 3. raster colour areas
        cover_boxes = canva_covers(page, covers)
        cover_rects = [r for r, _, _ in cover_boxes]
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
                        it["connects"] = sorted(set(re.findall(r"\d", lab)) - {fid})
                items.append(it)
            st[key["name"]] = len(regs)
        for rgb, area in unkeyed_colours(plan, scale, CFG["rasterKey"] + CFG["ignoreRaster"], exclude):
            issue(fname, f"Colour #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X} covers ~{area:.0f} pt² but is not in the colour key.")

        # the plan picture alone (with Canva's cover boxes). Above titleMaxY only
        # what shows on the page is kept: the plan's own logo there is covered
        # by Canva (and the label layer has no plan pixels to fade with the title)
        C = render(page, bscale)
        B = plan_only_render(doc, page, bscale, C, cover_boxes, clip_of(page, covers[0][0]) if covers else None)
        ty = int(CFG["titleMaxY"] * bscale)
        B[:ty][np.abs(C[:ty].astype(int) - B[:ty].astype(int)).max(2) > 8] = 255
        # per character, so a rotated label doesn't blank out a whole upright box
        text_boxes = [ch["bbox"] for blk in page.get_text("rawdict")["blocks"] if blk["type"] == 0
                      for ln in blk["lines"] for sp in ln["spans"] for ch in sp["chars"] if ch["c"].strip()]

        # 4. rooms
        rs, floor_rgb = room_settings()
        room_P = floor_masks(plan, scale, floor_rgb, rs.get("thinLinePt", 2.0), rs.get("doorLinePt", 10),
                             rs.get("thinWallDarkerThan", 170),
                             [d["line"] for d in rs.get("dividers", []) if d["floor"] == fid])
        no_shape = []
        for b in room_blocks:
            name, desc = tidy_name(b)
            poly, why = room_shape(room_P, (b["cx"], b["cy"]), W * H, name)
            it = {
                "id": new_id(f"room-{slug(name)}"), "floor": fid, "category": "rooms",
                "name": name, "aliases": [],
                "pin": [r1(b["cx"]), r1(b["cy"])],
                "labelBoxes": [xywh(b["bbox"])],
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
            elif why == "label is outside the building":
                # label outside the building: follow its leader lines to the rooms
                polys = []
                targets = leader_targets(C, B, bscale, b["bbox"], text_boxes)
                for (ex, ey), (ux, uy) in targets:
                    def known(q):
                        return any(math.dist(np.mean(q, 0), np.mean(o, 0)) < 5 for o in polys)
                    # first: the room just behind the wall the line ends on;
                    # if none (or already found): the indoor room nearest the line's end
                    seed = behind_wall(plan, scale, (ex, ey), (ux, uy))
                    pp = room_near(room_P, seed, W * H, radius=4) if seed else None
                    if not pp or known(pp):
                        pp = room_near(room_P, (ex, ey), W * H)
                    if pp and not known(pp):
                        polys.append(pp)
                if polys:
                    cx, cy = np.mean([np.mean(q, 0) for q in polys], 0)
                    best = min(polys, key=lambda q: math.dist(np.mean(q, 0), (cx, cy)))
                    m = np.zeros((int(H * scale), int(W * scale)), np.uint8)
                    cv2.fillPoly(m, [(np.array(best) * scale).astype(np.int32)], 1)
                    it["pin"] = inside_point(m, scale)
                    xs = [b["bbox"][0], b["bbox"][2]] + [t[0][0] for t in targets]
                    ys = [b["bbox"][1], b["bbox"][3]] + [t[0][1] for t in targets]
                    it["labelBoxes"] = [xywh((min(xs), min(ys), max(xs), max(ys)))]
                    if len(polys) == 1:
                        it["shape"] = {"type": "polygon", "points": polys[0]}
                    else:
                        it["shapes"] = [{"type": "polygon", "points": q} for q in polys]
                    issue(fname, f"{name}: label is outside the building; followed its lines to {len(polys)} room(s). Check on the review picture.")
                else:
                    no_shape.append(f"{name} ({why}; no lines to follow)")
            else:
                no_shape.append(f"{name} ({why})")
            items.append(it)
        st["rooms"] = len(room_blocks)
        st["rooms with outline"] = len(room_blocks) - len(no_shape)
        if no_shape:
            issue(fname, "Rooms without an outline (pin only, at the label): " + "; ".join(no_shape))

        # 5. "To floor …" / lift floor numbers belong to the nearest stairs or lift
        movers = [it for it in items[first_item:] if it["category"] in ("stairs", "lifts") and "shape" in it]
        for b in notes:
            best, bd = None, 45
            for it in movers:
                xs = [p[0] for p in it["shape"]["points"]]
                ys = [p[1] for p in it["shape"]["points"]]
                dd = rect_dist(b["cx"], b["cy"], (min(xs), min(ys), max(xs), max(ys)))
                if dd < bd:
                    best, bd = it, dd
            if best:
                best.setdefault("labelBoxes", []).append(xywh(b["bbox"]))
                # the floors it goes to ("To floors 1 & 3", "0, 1, 2") -> connects
                dest = set(best.get("connects", [])) | set(re.findall(r"\d", b.get("text", "")))
                best["connects"] = sorted(dest - {fid})

        # 6. layers: muted plan, full-colour plan (the Canva layer is written after the overrides are merged)
        Image.fromarray(mute(B)).save(MAPS_DIR / f"{fid}.webp", "WEBP", quality=74, method=6)
        Image.fromarray(B).save(MAPS_DIR / f"{fid}-full.webp", "WEBP", quality=74, method=6)
        # the same two for dark mode
        Image.fromarray(darken(B, muted=True)).save(MAPS_DIR / f"{fid}-dark.webp", "WEBP", quality=74, method=6)
        Image.fromarray(darken(B)).save(MAPS_DIR / f"{fid}-full-dark.webp", "WEBP", quality=74, method=6)
        # what the label layer needs (written after the overrides are merged)
        layers_todo.append({
            "page": page, "fid": fid,
            "plan_seq": {cs for cs, _ in covers}, "covers": covers,
            "drop": {d["seqno"] for d in arrows} | {q for _, _, seqs in cover_boxes for q in seqs},
            "sel": sel, "chrome": chrome, "pins": [p["seqs"] for p in mpins],
        })

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
    OUT_GEN.write_text(json.dumps(generated, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (RASTER_DIR / "rasters.json").write_text(json.dumps(raster_meta, indent=1) + "\n", encoding="utf-8")

    final, merge_notes = merge(generated)
    # 7. the Canva layer as SVG, tagged with the final items (overrides can add labelBoxes)
    for L in layers_todo:
        here = [it for it in final["items"] if it["floor"] == L["fid"]]
        sel = {k: v for k, v in L["sel"].items() if any(it["id"] == v for it in here)}
        svg = label_layer(L["page"], L["fid"], L["plan_seq"], L["covers"], L["drop"], sel,
                          L["chrome"], L["pins"], here)
        (MAPS_DIR / f"{L['fid']}-labels.svg").write_text(svg, encoding="utf-8", newline="\n")
    OUT_FINAL.parent.mkdir(exist_ok=True)
    OUT_FINAL.write_text(json.dumps(final, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for n in merge_notes:
        issue("overrides", n)

    draw_review(doc, generated, final)
    write_report(stats, generated, final)
    print(f"Wrote {OUT_FINAL.relative_to(ROOT)} ({len(final['items'])} items), report: {OUT_REPORT.relative_to(ROOT)}")
    # 8. link previews: a page per item (p/<id>/) and a small picture per floor
    if OUT_FINAL == ROOT / "data/overlay.json":
        subprocess.call([sys.executable, str(ROOT / "scripts/pages.py")])
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
    ovr = json.loads(OUT_OVR.read_text(encoding="utf-8")) if OUT_OVR.exists() else {}
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
            for sh in ([it["shape"]] if "shape" in it else []) + it.get("shapes", []):
                if sh["type"] == "rect":
                    pts = [(sh["x"], sh["y"]), (sh["x"] + sh["width"], sh["y"]),
                           (sh["x"] + sh["width"], sh["y"] + sh["height"]), (sh["x"], sh["y"] + sh["height"])]
                else:
                    pts = sh["points"]
                pts = [(x * s, y * s) for x, y in pts]
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
         "- Room outlines are traced from the plan around each room label: squares are fitted between the walls (so corners "
         "stay square and doorways are cut along the wall line), door swings count as room. Open areas without a wall "
         "between rooms need a divider in `scripts/import-config.json` (`roomShapes.dividers`); without one they get a pin only.", "",
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
    OUT_REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
