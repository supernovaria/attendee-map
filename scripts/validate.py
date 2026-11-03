#!/usr/bin/env python3
"""Check an overlay file before publishing.

    python3 scripts/validate.py              # checks data/overlay.json
    python3 scripts/validate.py other.json

Checks the JSON Schema (schema/overlay.schema.json) plus things a schema
cannot: references between floors/categories/items, unique ids, coordinates
inside the floor, and that background files exist.
Exit code 0 = OK, 1 = problems found.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/overlay.json"
    errors, warnings = [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: cannot read {path}: {e}")
        return 1

    try:
        import jsonschema
        schema = json.loads((ROOT / "schema/overlay.schema.json").read_text(encoding="utf-8"))
        v = jsonschema.Draft202012Validator(schema)
        for e in sorted(v.iter_errors(data), key=lambda e: list(e.path)):
            errors.append(f"schema: {'/'.join(map(str, e.path)) or '(root)'}: {e.message}")
    except ImportError:
        warnings.append("jsonschema not installed (pip install jsonschema) - schema check skipped, reference checks still run")

    if errors:  # structure is broken; reference checks would only add noise
        return report(path, errors, warnings)

    def dupes(xs):
        seen, d = set(), set()
        for x in xs:
            (d if x in seen else seen).add(x)
        return d

    floors = {f["id"]: f for f in data["floors"]}
    cats = {c["id"] for c in data["categories"]}
    for kind, xs in (("floor", data["floors"]), ("category", data["categories"]), ("item", data["items"])):
        for d in dupes(x["id"] for x in xs):
            errors.append(f"duplicate {kind} id '{d}'")

    site_root = path.resolve().parent.parent if path.resolve().parent.name == "data" else ROOT
    for f in data["floors"]:
        for key in ("background", "backgroundHighlight", "labels"):
            if key in f and not (site_root / f[key]).exists():
                errors.append(f"floor '{f['id']}': {key} file '{f[key]}' not found")
            dk = f.get("dark", {})
            if key in dk and not (site_root / dk[key]).exists():
                errors.append(f"floor '{f['id']}': dark.{key} file '{dk[key]}' not found")
    for c in data["categories"]:
        if "floor" in c and c["floor"] not in floors:
            errors.append(f"category '{c['id']}': floor '{c['floor']}' does not exist")

    used = set()
    for it in data["items"]:
        iid = it["id"]
        used.add(it["category"])
        if it["floor"] not in floors:
            errors.append(f"item '{iid}': floor '{it['floor']}' does not exist")
            continue
        if it["category"] not in cats:
            errors.append(f"item '{iid}': category '{it['category']}' does not exist")
        f = floors[it["floor"]]
        pts = [it["pin"]]
        for sh in ([it["shape"]] if it.get("shape") else []) + it.get("shapes", []):
            if sh["type"] == "polygon":
                pts += sh["points"]
            elif sh["type"] == "rect":
                pts += [[sh["x"], sh["y"]], [sh["x"] + sh["width"], sh["y"] + sh["height"]]]
        for x, y in pts:
            if not (0 <= x <= f["width"] and 0 <= y <= f["height"]):
                errors.append(f"item '{iid}': point ({x}, {y}) is outside floor '{f['id']}' ({f['width']} x {f['height']})")
                break
    for c in data["categories"]:
        if c["id"] not in used:
            warnings.append(f"category '{c['id']}' has no items (its chip will show 'not on any floor')")
    return report(path, errors, warnings)


def report(path, errors, warnings) -> int:
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(("FAIL" if errors else "OK") + f": {path} ({len(errors)} error(s), {len(warnings)} warning(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
