"""Validate the use-case corpus (data/usecases/catalog.yaml) against the primitive
vocabulary, map every case to a builder kernel, and print coverage matrices.

This is the "test each combination" step: if every catalog entry passes, the
primitive set + kernel set provably covers the whole product catalog, and the
builder only has to implement the kernels — not one handler per use case.

Usage:  python scripts/validate_usecases.py [--csv out.csv]
Exit code 1 if any use case fails validation (unknown primitive, missing field,
or no kernel can express it).
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "usecases" / "catalog.yaml"

REQUIRED_FIELDS = ["id", "name", "vertical", "models", "classes", "custom_classes",
                   "rule", "uses", "fps"]

# Which spatial primitive is served by which builder kernel. A use case is
# expressible iff every spatial primitive it uses maps to a kernel.
KERNEL_OF = {
    "presence": "zone_state",
    "absence": "zone_state",
    "count": "zone_state",
    "line_cross": "line_cross",
    "dwell": "dwell",
    "proximity": "proximity",
    "vanish": "object_lifecycle",
    "stationary": "object_lifecycle",
    "posture": "posture",
    "identity": "identity",
    "attribute": "attribute",
}
# join/temporal primitives are decorators available to every kernel;
# `correlate` and `aggregate` run downstream of kernels on the event stream.


def fail(msgs: list[str], uc_id: str, msg: str) -> None:
    msgs.append(f"  ✗ {uc_id}: {msg}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="also write the flat decomposition matrix as CSV")
    args = ap.parse_args()

    data = yaml.safe_load(CATALOG.read_text())
    vocab = data["vocabulary"]
    usecases = data["usecases"]
    errors: list[str] = []

    kernel_counts: Counter[str] = Counter()
    kernel_by_vertical: dict[str, Counter] = defaultdict(Counter)
    prim_counts: dict[str, Counter] = {k: Counter() for k in ("spatial", "temporal", "join", "sink")}
    model_counts: Counter[str] = Counter()
    custom_unlocks: dict[str, list[str]] = defaultdict(list)
    combo_counts: Counter[tuple] = Counter()
    rows = []

    ids_seen = set()
    for uc in usecases:
        uid = uc.get("id", "<missing id>")
        if uid in ids_seen:
            fail(errors, uid, "duplicate id")
        ids_seen.add(uid)

        for f in REQUIRED_FIELDS:
            if f not in uc:
                fail(errors, uid, f"missing field '{f}'")
        if not isinstance(uc.get("fps"), (int, float)) or uc.get("fps", 0) <= 0:
            fail(errors, uid, "fps must be a positive number")

        for m in uc.get("models", []):
            if m not in vocab["models"]:
                fail(errors, uid, f"unknown model '{m}'")
            model_counts[m] += 1

        uses = uc.get("uses", {})
        kernels = set()
        for cat in ("spatial", "temporal", "join", "sink"):
            for p in uses.get(cat, []):
                if p not in vocab[cat]:
                    fail(errors, uid, f"unknown {cat} primitive '{p}'")
                else:
                    prim_counts[cat][p] += 1
            if cat == "spatial":
                for p in uses.get(cat, []):
                    k = KERNEL_OF.get(p)
                    if k is None and p in vocab[cat]:
                        fail(errors, uid, f"spatial primitive '{p}' has no kernel — builder cannot express this case")
                    elif k:
                        kernels.add(k)
        if uses.get("join"):
            kernels.add("correlate")
        if {"rate"} & set(uses.get("temporal", [])) or {"report", "heatmap"} & set(uses.get("sink", [])):
            kernels.add("aggregate")
        if not kernels:
            fail(errors, uid, "no kernels inferred — empty spatial uses?")

        vertical = uc.get("vertical", "?")
        for k in kernels:
            kernel_counts[k] += 1
            kernel_by_vertical[vertical][k] += 1
        for c in uc.get("custom_classes", []):
            custom_unlocks[c].append(uid)
        combo_counts[tuple(sorted(k for k in kernels if k not in ("aggregate", "correlate")))] += 1

        rows.append({
            "id": uid, "vertical": vertical, "fps": uc.get("fps"),
            "models": "|".join(uc.get("models", [])),
            "custom_classes": "|".join(uc.get("custom_classes", [])),
            "kernels": "|".join(sorted(kernels)),
            "spatial": "|".join(uses.get("spatial", [])),
            "temporal": "|".join(uses.get("temporal", [])),
            "join": "|".join(uses.get("join", [])),
            "sink": "|".join(uses.get("sink", [])),
        })

    n = len(usecases)
    verticals = sorted({uc["vertical"] for uc in usecases})
    print(f"catalog: {n} use cases, {len(verticals)} verticals")
    print()

    print("── kernel coverage (use cases each kernel serves) ──")
    for k, c in kernel_counts.most_common():
        print(f"  {k:<16} {c:>3}  ({100 * c / n:.0f}%)")
    print()

    print("── kernel × vertical matrix ──")
    kernels_sorted = [k for k, _ in kernel_counts.most_common()]
    header = f"  {'vertical':<12}" + "".join(f"{k[:9]:>10}" for k in kernels_sorted)
    print(header)
    for v in verticals:
        row = f"  {v:<12}" + "".join(f"{kernel_by_vertical[v].get(k, 0) or '·':>10}" for k in kernels_sorted)
        print(row)
    print()

    print("── most common kernel combinations (the builder's presets) ──")
    for combo, c in combo_counts.most_common(12):
        print(f"  {c:>3}×  {' + '.join(combo) if combo else '(decorator-only)'}")
    print()

    print("── primitive frequency ──")
    for cat, counts in prim_counts.items():
        line = ", ".join(f"{p}:{c}" for p, c in counts.most_common())
        print(f"  {cat:<9} {line}")
    print()

    print("── model mix ──")
    for m, c in model_counts.most_common():
        print(f"  {m:<12} {c:>3} use cases")
    print()

    print("── custom-training backlog (classes ranked by use cases unlocked) ──")
    ranked = sorted(custom_unlocks.items(), key=lambda kv: -len(kv[1]))
    for cls, ucs in ranked:
        print(f"  {cls:<22} unlocks {len(ucs):>2}: {', '.join(ucs[:4])}{'…' if len(ucs) > 4 else ''}")
    print()

    coco_only = sum(1 for uc in usecases
                    if not uc.get("custom_classes") and set(uc["models"]) <= {"det.coco"})
    coco_plus = sum(1 for uc in usecases if not uc.get("custom_classes"))
    print(f"day-one (pure COCO detector): {coco_only}/{n}")
    print(f"no custom training needed (COCO + face/pose/ocr): {coco_plus}/{n}")
    print()

    if args.csv:
        out = Path(args.csv)
        with out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote decomposition matrix → {out}")

    if errors:
        print(f"FAILED — {len(errors)} problem(s):")
        print("\n".join(errors))
        return 1
    print(f"OK — all {n} use cases validate and map to kernels. Every combination is expressible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
