#!/usr/bin/env python3
"""Link previews: one small page per item, so a pasted link shows what it points to.

    python3 scripts/pages.py            # write p/<item id>/index.html, maps/<floor>-preview.jpg, index.html's preview block
    python3 scripts/pages.py --check    # only report what is missing or out of date (validate.py runs this)

Slack, WhatsApp etc. read a link's title and picture from the page's <head>
without running the map's code, and GitHub Pages serves the same index.html
for every ?item= link. So every item gets its own copy of index.html at
p/<item id>/ (a full copy, not a redirect: no extra step when it opens) with
its own title and a picture of its floor. A <base> line makes the copy load
everything else from the site root, so the map, data and pictures are shared
and cached once. app.js reads the item from the address.

Settings: linkPreview in scripts/import-config.json. import.py runs this at the end.
Re-run it after editing index.html (validate.py says so if you forget).
"""
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "p"
BLOCK = re.compile(r"(<!-- link preview:[^\n]*-->\n)(.*?)(<!-- /link preview -->)", re.S)
GENERATED = '<meta name="generator" content="scripts/pages.py">'


def text(path):
    """File contents with \\n line ends (git on Windows may check files out with \\r\\n)."""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def settings():
    cfg = json.loads((ROOT / "scripts/import-config.json").read_text(encoding="utf-8"))
    lp = cfg["linkPreview"]
    url = lp["siteUrl"].rstrip("/") + "/"
    return url, lp["siteName"], lp["description"], lp.get("previewWidthPx", 630)


def head_block(title, desc, url, image, site_name, size):
    a = lambda s: html.escape(s, quote=True)  # noqa: E731
    w, h = size
    return (
        f"<title>{html.escape(title)}</title>\n"
        f'<meta name="description" content="{a(desc)}">\n'
        f'<meta property="og:site_name" content="{a(site_name)}">\n'
        f'<meta property="og:title" content="{a(title)}">\n'
        f'<meta property="og:description" content="{a(desc)}">\n'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:url" content="{a(url)}">\n'
        f'<meta property="og:image" content="{a(image)}">\n'
        f'<meta property="og:image:width" content="{w}">\n'
        f'<meta property="og:image:height" content="{h}">\n'
        f'<meta name="twitter:card" content="summary_large_image">\n'
    )


def preview_size(width):
    meta = json.loads((ROOT / "source/raster/rasters.json").read_text(encoding="utf-8"))
    m = next(iter(meta.values()))
    return width, round(width * m["heightPx"] / m["widthPx"])


def previews(width, write):
    """maps/<floor>-preview.jpg: the printed floor (page render, labels and all), small."""
    meta = json.loads((ROOT / "source/raster/rasters.json").read_text(encoding="utf-8"))
    out = {}
    for fid, m in meta.items():
        dst = ROOT / "maps" / f"{fid}-preview.jpg"
        out[fid] = dst
        if write:
            from PIL import Image
            im = Image.open(ROOT / m["file"]).convert("RGB")
            im = im.resize(preview_size(width), Image.LANCZOS)
            im.save(dst, "JPEG", quality=82, optimize=True, progressive=True)
    return out


def goes_to(it, floors):
    """Stairs and lifts: "Goes to the 2nd and 3rd floors" from connects (same wording as goesTo in app.js)."""
    fs = sorted((floors[i] for i in it.get("connects") or [] if i in floors), key=lambda f: f.get("order", 0))
    w = [(f.get("shortName") or f["name"]).lower().removesuffix(" floor") for f in fs]
    if not w:
        return ""
    lst = f"{', '.join(w[:-1])} and {w[-1]}" if len(w) > 1 else w[0]
    return f"Goes to the {lst} floor{'s' if len(w) > 1 else ''}"


def item_text(it, floors, cats):
    floor = floors[it["floor"]]["name"]
    extra = " · ".join(x for x in (goes_to(it, floors), it.get("description")) if x) or cats.get(it["category"], "")
    return it["name"], f"{floor} · {extra}" if extra and extra != it["name"] else floor


def build(write=True):
    """Returns the problems found (with write=False: what --check would change)."""
    url, site_name, site_desc, width = settings()
    data = json.loads((ROOT / "data/overlay.json").read_text(encoding="utf-8"))
    floors = {f["id"]: f for f in data["floors"]}
    cats = {c["id"]: c["label"] for c in data["categories"]}
    size = preview_size(width)
    pics = previews(width, write)
    problems = []

    index_path = ROOT / "index.html"
    index = text(index_path)
    if not BLOCK.search(index):
        return ["index.html has no '<!-- link preview: ... -->' block"]
    first = data["floors"][0]["id"]
    root_block = head_block(site_name, site_desc, url, f"{url}maps/{first}-preview.jpg", site_name, size)
    new_index = BLOCK.sub(lambda m: m.group(1) + root_block + m.group(3), index, count=1)

    want = {}
    for it in data["items"]:
        if it["floor"] not in pics:
            problems.append(f"item '{it['id']}': no preview picture for floor '{it['floor']}'")
            continue
        title, desc = item_text(it, floors, cats)
        block = head_block(title, desc, f"{url}p/{it['id']}/", f"{url}maps/{it['floor']}-preview.jpg", site_name, size)
        page = BLOCK.sub(lambda m: m.group(1) + block + m.group(3), new_index, count=1)
        # everything else (style.css, app.js, data, maps) comes from the site root
        page = page.replace('<meta charset="utf-8">\n', f'<meta charset="utf-8">\n<base href="../../">\n{GENERATED}\n', 1)
        want[it["id"]] = page

    stale = [d for d in PAGES_DIR.iterdir() if d.is_dir() and d.name not in want] if PAGES_DIR.exists() else []
    if write:
        index_path.write_text(new_index, encoding="utf-8", newline="\n")
        for iid, page in want.items():
            d = PAGES_DIR / iid
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text(page, encoding="utf-8", newline="\n")
        for d in stale:  # items that no longer exist (only folders this script made)
            f = d / "index.html"
            if f.exists() and GENERATED in f.read_text(encoding="utf-8"):
                shutil.rmtree(d)
        return problems

    if new_index != index:
        problems.append("index.html: link preview block is out of date")
    for fid, p in pics.items():
        if not p.exists():
            problems.append(f"maps/{p.name} is missing")
    missing = [i for i in want if not (PAGES_DIR / i / "index.html").exists()]
    old = [i for i, page in want.items() if i not in missing
           and text(PAGES_DIR / i / "index.html") != page]
    for what, ids in (("missing", missing), ("out of date", old)):
        if ids:
            problems.append(f"{len(ids)} item page(s) {what}: " + ", ".join(f"p/{i}/" for i in ids[:5]) + (" …" if len(ids) > 5 else ""))
    for d in stale:
        problems.append(f"p/{d.name}/ belongs to no item")
    return problems


def main():
    check = "--check" in sys.argv
    problems = build(write=not check)
    for p in problems:
        print(("ERROR: " if check else "warning: ") + p)
    if check and problems:
        print("Run: python3 scripts/pages.py")
        return 1
    if not check:
        n = len(list(PAGES_DIR.glob("*/index.html")))
        print(f"Wrote {n} item pages in p/, preview pictures in maps/, and index.html's preview block")
    return 0


if __name__ == "__main__":
    sys.exit(main())
