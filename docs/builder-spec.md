# VisionSense Builder Spec

*Derived from the full use-case corpus in [`data/usecases/catalog.yaml`](../data/usecases/catalog.yaml)
(100 use cases, 13 verticals). Coverage proven by `scripts/validate_usecases.py` —
every catalog item decomposes into the fixed vocabulary below and maps to a kernel.*

## 1. The pattern (what the corpus taught us)

Every sellable app is the same four-stage sentence:

```
PERCEIVE (model + classes) → TRACK (ByteTrack IDs) → CONDITION (rule) → EMIT (sink)
```

The pipeline already implements PERCEIVE→TRACK ([src/pipeline.py](../src/pipeline.py)).
What varies per product is only the CONDITION and the EMIT — and the corpus shows the
condition space is small:

- **11 spatial primitives** (presence, absence, count, line_cross, dwell, proximity,
  vanish, stationary, posture, identity, attribute)
- **6 temporal decorators** (sustained, schedule, rate, edge, cooldown, duration)
- **3 joins** (list_match, roster_compare, event_correlate)
- **6 sinks** (alert, log, metric, heatmap, report, signal)

No catalog item needed anything outside this vocabulary. **The builder therefore
implements 10 kernels, not 100 handlers.**

## 2. The 10 kernels (measured coverage)

| Kernel | Spatial primitives | Coverage | Replaces / examples |
|---|---|---|---|
| `zone_state` | presence, absence, count | 72% | intrusion, unmanned counter, occupancy, queue, crowd density, fire presence, bed occupancy — and existing `headcount`, `desk_activity` |
| `aggregate` | (event-stream rollups) | 40% | hourly footfall reports, heatmaps, shift reports — runs downstream of other kernels |
| `correlate` | (join decorators) | 26% | POS-less exit, tailgating vs badge, dispatch-order mismatch, drive-off vs payment |
| `line_cross` | line_cross | 21% | footfall, box/sack counting, perimeter, bus on/off |
| `proximity` | proximity | 17% | phone-in-hand, forklift near-miss, lost child, abandoned-bag ownership |
| `identity` | identity | 16% | face attendance, ALPR, VIP/watchlist, cattle ID, guard patrol |
| `dwell` | dwell | 14% | loitering, aisle heatmap source, idle time, handwash timer, wait time |
| `attribute` | attribute | 14% | PPE/uniform/mask state, machine-on, age/gender, drawer-open, covered face |
| `object_lifecycle` | vanish, stationary | 7% | theft (existing `theft` handler), abandoned object, blocked fire exit |
| `posture` | posture | 6% | fall, man-down, fight, animal-down, escalator fall |

Most common combinations (= builder **presets**): `zone_state` alone (25×),
`attribute+zone_state` (10×), `identity+zone_state` (8×), `line_cross+zone_state` (7×),
`dwell+zone_state` (7×), `proximity+zone_state` (6×), `identity+line_cross` / ALPR (5×).

Temporal decorators are near-universal: `cooldown` appears in 56 cases, `sustained` in
48, `schedule` in 26 — these belong in the kernel **base class**, not per-kernel code.
Sink mix: alert 77, report 39, log 36, metric 34, signal 14 — alert delivery (WhatsApp
snapshot + cooldown) is the single highest-leverage shared component.

## 3. Rule schema (what the builder generates)

One generic `RuleHandler` replaces the per-name registry in
[src/logic/\_\_init\_\_.py](../src/logic/__init__.py). A camera's `logic:` list becomes a
list of rule configs:

```yaml
# config/rules/counter_unmanned.yaml
id: retail.counter-unmanned
kernel: zone_state
detect: {classes: [person]}
condition:
  state: absence            # presence | absence | count{op,value}
  zone: counter
temporal:
  sustained: 300            # hold ≥ 5 min before firing
  schedule: business_hours  # named window from site config
  cooldown: 600
emit:
  - alert: {channel: whatsapp, snapshot: true}
```

```yaml
# config/rules/forklift_nearmiss.yaml
id: warehouse.forklift-nearmiss
kernel: proximity
detect: {classes: [person], custom: [forklift]}
condition: {a: forklift, b: person, max_dist_px: 200}
temporal: {sustained: 1, cooldown: 30, rate: {bucket: shift}}
emit:
  - alert: {channel: whatsapp, snapshot: true}
  - signal: {output: siren}
  - report: {name: near_miss}
```

```yaml
# config/rules/gate_alpr.yaml
id: residential.gate-alpr
kernel: identity
detect: {classes: [car], custom: [license_plate]}
secondary: {model: ocr, on: license_plate}
condition: {zone: gate}
join: {list_match: resident_list, on_match: [signal: open_gate, log: entry],
       on_miss: [log: visitor, alert: {to: guard}]}
temporal: {cooldown: 60}
```

Schema skeleton: `kernel` (one of 10) + `detect` + `condition` (kernel-specific, small)
+ `temporal` (shared decorators) + optional `join`/`secondary` + `emit` (list of sinks).
The builder UI is then: pick a preset → draw zones/lines → set thresholds & schedule →
choose alert channel. That is the whole product configurator.

## 4. Build order (highest leverage first)

1. **Kernel base class** with the temporal decorators (sustained/schedule/cooldown/edge/
   duration) — every existing handler re-derives these by hand today.
2. **`zone_state` kernel** — alone covers 72% of the catalog and subsumes
   `headcount` + `desk_activity`.
3. **Alert sink** (WhatsApp snapshot + cooldown) — appears in 77/100 cases; it's the
   feature clients buy.
4. **`aggregate` sink service** (rate buckets → metric/report/heatmap) — 40%.
5. `line_cross`, `dwell`, `proximity` kernels — pure geometry on existing tracks, no new
   models.
6. `object_lifecycle` — port the existing `theft` handler into the generic form.
7. `identity` (face.embed + list_match) — the universal door-opener (attendance), 16%.
8. `attribute` (secondary classifier on track crops) — unlocks all PPE/uniform SKUs.
9. `posture` (YOLO-pose) and `correlate` (external event join) last.

## 5. Model & training roadmap (from the corpus)

- **34/100 use cases ship day-one** with the pretrained COCO detector alone;
  **52/100** with COCO + face/pose/OCR (still zero custom labeling).
- Custom-training backlog ranked by use cases unlocked:
  `license_plate` (4), `gloves`/`cigarette`/`cattle` (3 each), then
  fire+smoke, mask, helmet, staff_uniform, carton, broken_seal, rodent, mop (2 each).
  A single **PPE pack** (helmet, vest, gloves, mask, hairnet, apron) unlocks factory,
  food, and hospital compliance SKUs at once — train it as one multi-class dataset.
- Per-camera FPS hints in the corpus feed the capacity planner directly: alert-grade
  rules run at 1–5 fps, counting lines at 8–15, visual QC at 25, shelf/parking scans at
  0.1–0.5. Combined with `model_ladder.csv`, that prices a site's GPU
  (see `combinations.csv` — the S1 OOM row shows why the fps hints matter).

## 6. Artifacts

- [`data/usecases/catalog.yaml`](../data/usecases/catalog.yaml) — the corpus: all 100
  use cases in the fixed vocabulary (the builder's acceptance-test set).
- [`data/usecases/decomposition_matrix.csv`](../data/usecases/decomposition_matrix.csv)
  — flat matrix (id × kernels × primitives × models × fps) for analysis/pricing sheets.
- `scripts/validate_usecases.py` — re-run after editing the catalog or adding
  primitives; CI-able (exit 1 on any unexpressible case).
