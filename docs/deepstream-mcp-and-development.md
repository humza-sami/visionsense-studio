# DeepStream MCP + Development Guide

How to use the AI-assisted DeepStream tooling, how it works, how to build real
applications on top of a DeepStream pipeline, and which language/stack to use for the
best performance. Written for someone new to the framework.

---

## 0. Two different "AI helpers" for DeepStream — don't confuse them

NVIDIA ships **two** separate AI-assist tools. They do different jobs:

| Tool | Type | What it does | When you use it |
|---|---|---|---|
| **Inference Builder MCP** | An **MCP server** (a backend the AI assistant calls) | Turns "make me a detection pipeline" into actual config files, Docker images, and runnable code | To *scaffold/generate* a new pipeline fast |
| **DeepStream coding-agent skill** | A **skill** (reference docs the AI reads) | Gives the assistant correct DeepStream API knowledge so hand-written code is accurate | To *hand-write or fix* pipeline code |

This project has the **Inference Builder MCP** installed and registered. This doc focuses
on it, then on how to build apps regardless of which tool you used.

---

## 1. What is MCP (Model Context Protocol)?

**MCP is a standard way for an AI assistant (like Claude/Cursor) to call external tools.**

Think of the AI as a smart office worker. On its own it can only *talk*. MCP gives it a
**set of buttons it can press** — "generate this file," "build this Docker image," "run
this container." Each button is a **tool** with defined inputs and outputs. The AI decides
*when* to press which button based on your plain-English request.

```
You (plain English)  →  AI assistant  →  [MCP tool: generate_nvinfer_config]  →  a real file appears
```

An **MCP server** is the little program that exposes those buttons. Ours runs from
`~/Personal/inference_builder/mcp/mcp_server.py` and is registered in this repo's
[`.mcp.json`](../.mcp.json):

```json
{
  "mcpServers": {
    "deepstream-inference-builder": {
      "command": ".../inference_builder/.venv/bin/python",
      "args": [".../inference_builder/mcp/mcp_server.py"]
    }
  }
}
```

When the AI assistant starts in this folder, it reads that file, launches the server, and
the tools become available. You never call the server directly — you ask the assistant.

---

## 2. The Inference Builder MCP — what it actually does

Source: [github.com/NVIDIA-AI-IOT/inference_builder](https://github.com/NVIDIA-AI-IOT/inference_builder).
It exposes **5 tools** (buttons):

| Tool | What it generates | Analogy |
|---|---|---|
| `prepare_model_repository` | Downloads a model (from NGC/HuggingFace) and lays out its folder | "Go fetch the ingredients" |
| `generate_nvinfer_config` | The `nvinfer` config file (like our `pgie_yolo26n.txt`) | "Write the recipe card" |
| `generate_inference_pipeline` | A full deployable project from one YAML — serving code, API, Dockerfile | "Build the whole kitchen" |
| `build_docker_image` | Builds the Docker image for that pipeline | "Package the kitchen in a box" |
| `docker_run_image` | Runs the built image to test it | "Turn it on and taste-test" |

### How it works internally

The builder is a **code generator**, not a runtime. You describe *what* you want in a
small YAML file; it stamps out all the boilerplate DeepStream/GStreamer/Triton code that
would take a human days to write correctly. Flow:

```
YAML spec  →  generate_inference_pipeline  →  a project folder (Python pipeline + Dockerfile + API)
                                            →  build_docker_image  →  a container
                                            →  docker_run_image    →  running service
```

It supports object-detection models (YOLO, DETR/RT-DETR, GroundingDINO) and can target
different "server types": `serverless` (batch job), `fastapi` (HTTP microservice),
`triton`, or `nim`.

### What it is good for — and its limits

- ✅ **Great for scaffolding**: getting a correct, runnable pipeline for a new model in
  minutes instead of fighting GStreamer element linking by hand.
- ✅ **Great for the config/parser boilerplate** that's easy to get subtly wrong.
- ⚠️ **It generates a starting point.** The disclaimer from NVIDIA is explicit: all
  generated code must go through your own review, testing, and security validation before
  production.
- ⚠️ **It does not build your business logic.** It gives you "detect objects and serve
  results." The *app* (dwell time, theft, PPE) is yours to write on top (Part 4).

---

## 3. Setup & usage

### Setup (already done in this project)

```bash
git clone https://github.com/NVIDIA-AI-IOT/inference_builder.git
cd inference_builder && python3 -m venv .venv && .venv/bin/pip install mcp <deps>
.venv/bin/python mcp/setup_mcp.py /path/to/your_project/.mcp.json   # registers the server
# restart the AI assistant → tools appear
```

Verify it is connected: in Claude Code run `/mcp`; you should see
`deepstream-inference-builder`. In Cursor: Settings → MCP → green dot.

### Usage — you just ask in plain English

You never call the tools directly. You describe the goal; the assistant picks the tools:

> "Generate a DeepStream object-detection pipeline for my YOLO26 ONNX at
> `models/yolo26n.onnx`, FP16, 640×640, and give me the nvinfer config."

The assistant will call `prepare_model_repository` → `generate_nvinfer_config` →
optionally `generate_inference_pipeline`, and drop real files in your project. (This is
exactly how the `pgie_*.txt` configs in `models/deepstream/app_configs/` were seeded.)

**Rule of thumb:** use the MCP to *bootstrap* a pipeline for a new model or a new server
type, then hand-tune the generated configs (batch size, `interval`, tracker) and add your
app code.

---

## 4. Building an application on top of DeepStream

This is the part that turns "a demo" into "a product." The MCP/generated pipeline gives
you **detections**; your app turns detections into **decisions**.

### 4.1 The one concept that matters: metadata + probes

After the pipeline detects and tracks, every frame carries a **metadata packet**: a list
of objects, each with `class_id`, bounding box, confidence, and a **persistent
`object_id`** (track ID). You attach a small function — a **probe** — to read that packet
as it flows past, and run your rule:

```python
def on_frame(pad, info):
    batch = pyds.gst_buffer_get_nvds_batch_meta(...)
    for frame in frames(batch):
        for obj in objects(frame):
            cls, box, tid = obj.class_id, bbox(obj), obj.object_id
            #  ← YOUR RULE (overlap? dwell? zone? line-cross?)
    return Gst.PadProbeReturn.OK

tracker.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, on_frame)
```

The heavy work (decode + inference + tracking) is already done on the GPU. Your rule is
cheap CPU arithmetic on a handful of numbers. **This is why apps are fast to build and
cheap to run.**

### 4.2 The universal app pattern

Every app — theft, PPE, footfall, dwell time, phone usage, intrusion — is the same four
steps (catalogued as 10 reusable "kernels" in [`builder-spec.md`](builder-spec.md)):

```
1. Filter objects by class        persons, chairs, phones, cars…
2. Test a spatial relationship     overlap? nearby? inside a zone? crossed a line?
3. Track over time by object_id    start timer / stop timer / count / accumulate
4. Emit when the rule fires        WhatsApp snapshot, database row, dashboard event
```

Worked example — **"time a person spent sitting on a chair"**:

```python
sit_since = {}                                   # object_id → time they sat down
def on_frame(pad, info):
    now = time.time()
    for frame in frames(batch):
        persons = [o for o in objects(frame) if o.class_id == 0]    # 0 = person
        chairs  = [o for o in objects(frame) if o.class_id == 56]   # 56 = chair
        for p in persons:
            sitting = any(iou(bbox(p), bbox(c)) > 0.3 for c in chairs)
            if sitting and p.object_id not in sit_since:
                sit_since[p.object_id] = now                        # sat down
            elif not sitting and p.object_id in sit_since:
                secs = now - sit_since.pop(p.object_id)             # stood up
                emit_event("chair_dwell", person=p.object_id, seconds=int(secs))
```

Swap `class_id == 56` (chair) for `67` (cell phone) and you have phone-usage timing. Swap
the overlap test for "inside a polygon" and you have zone intrusion. Same skeleton.

### 4.3 Where the app code lives

You have two ways to run a DeepStream pipeline *with your probe*:

1. **`deepstream-app` + config only** (what this repo uses for benchmarks/demo) — no custom
   code, no probes. Good for testing capacity, not for apps.
2. **A custom pipeline program** (Python `pyds`/`pyservicemaker`, or C++) — you build the
   same pipeline in code and `add_probe(...)` your rules. **This is where apps live.** The
   Inference Builder MCP can generate the skeleton of this program for you.

### 4.4 Running different models on different cameras (mixed models)

Common need: "10 cameras on YOLO-xlarge (critical), 20 on YOLO-small (cheap)." A single
`nvinfer` (PGIE) applies **one** model to **every** camera flowing through it — the
`[primary-gie]` block in a config points to one engine. So **one plain config file cannot
split models per camera.** Think of `nvinfer` as one AI inspection station on the belt;
everything on that belt gets the same model. There are two ways to get mixed models:

**Option A — Two pipelines (simple, recommended).** Run two `deepstream-app` instances,
each with its own config, on the **same GPU** — they share VRAM, decoder, and compute
automatically:

```
Pipeline 1:  pgie_yolo26x.txt  → 10 cameras → YOLO-xlarge   ┐  one GPU,
Pipeline 2:  pgie_yolo26s.txt  → 20 cameras → YOLO-small    ┘  two processes
```

This is the standard pattern for heterogeneous camera groups, not a workaround. It is
**validated on our hardware**: the mixed benchmark ran two containers (xlarge×15 +
small×25 = 40 cams) sharing one RTX 3070 Ti at full 30 fps, 14 % GPU, 65 % NVDEC, 4.3 GB
(see [`deepstream-benchmark-report.md`](deepstream-benchmark-report.md)). Two assembly
lines, one factory floor.

**Option B — One pipeline with parallel inference (advanced).** DeepStream can do it in a
single process by splitting the stream into per-model branches and merging the metadata
back:

```
cameras → nvstreammux → nvstreamdemux ─┬─→ nvinfer(xlarge) ─┐
                                       └─→ nvinfer(small)  ─┴─→ nvdsmetamux → tracker → out
```

This is NVIDIA's `deepstream-parallel-inference-app` pattern. It **cannot** be expressed in
the plain `deepstream-app` text config — you build the pipeline in code (Python
`pyservicemaker` or C++), which the Inference Builder MCP can scaffold.

| | Option A — two pipelines | Option B — parallel inference |
|---|---|---|
| Config | two text files | custom code (pyservicemaker / C++) |
| Effort | minutes | days |
| Runs on one GPU | ✅ | ✅ |
| Proven on our box | ✅ (15×x + 25×s run) | not yet |
| Use when | **almost always** | one unified process per box, or shared-batch overhead matters at huge scale |

**Recommendation:** use **Option A** unless you have a specific reason for one process. The
GPU is the same shared pool either way, and two configs are far simpler to run, quote, and
debug.

> **Not the same thing:** a **Secondary GIE (SGIE)** runs a *second model on the output of
> the first* (detect car → classify its colour) — chaining models on the same objects, not
> different models on different cameras. Don't reach for SGIE to solve mixed-camera-groups.

---

## 5. Best language / stack for efficiency

Short answer: **Python for orchestration and rules, C++ only for the hot inner loop
(parsers), and keep the heavy lifting inside DeepStream's GPU plugins.** Here's the
reasoning, layer by layer.

### 5.1 The golden rule

> **Never touch pixels in your own code.** Decode, inference, tracking, and drawing all
> happen inside NVIDIA's GPU plugins (C/CUDA). Your code only ever sees **metadata** — a
> few numbers per object. As long as that stays true, the language of *your* code barely
> affects performance.

The old VisionSense Python pipeline was slow precisely because it broke this rule (copied
pixels GPU→CPU→GPU). DeepStream keeps pixels on the GPU, so your Python is free to be
"slow" — it's only doing arithmetic on boxes.

### 5.2 Layer-by-layer recommendation

| Layer | Best choice | Why |
|---|---|---|
| **Decode / inference / tracking** | DeepStream GPU plugins (don't write this) | Already optimal C/CUDA; you only configure it |
| **Custom bbox parser** (per detection, per camera) | **C++** | Runs millions of times/sec; must be fast. This is the *only* place you're forced into C++. Small file (see our `nvdsinfer_yolo26.cpp`). |
| **Pipeline orchestration** (build & link the graph) | **Python (`pyservicemaker`)** or C++ | Runs once at startup. Python is far faster to write and just as fast at runtime (it only *builds* the graph; the graph runs in C). Use `pyservicemaker` (modern, cleaner) over raw `pyds` where possible. |
| **Rules engine / apps** (probes) | **Python** | Runs per-frame on metadata only (cheap). Python's readability wins; the math is trivial. If a rule ever gets heavy (thousands of objects × complex geometry), move that one function to C++/Cython. |
| **Alerts, dashboard, API, storage** | **Python (FastAPI)** — or **Go** for the always-on agent | Network/IO bound, not compute bound. FastAPI matches the rest of the Python stack; Go is worth it only for a tiny always-alive updater/watchdog. |
| **Message bus between pieces** | **Redis / Kafka** (DeepStream has a built-in `nvmsgbroker`) | Decouples detection from your app and dashboard |

### 5.3 The recommended stack (concrete)

```
┌── ON THE GPU BOX (per site) ─────────────────────────────────────────────┐
│  DeepStream pipeline (pyservicemaker, Python)                            │
│    NVDEC → nvstreammux → nvinfer(YOLO26 FP16, C++ parser) → nvtracker    │
│    → PROBE (Python rules engine: the 10 kernels)                         │
│    → events → nvmsgbroker / Redis                                        │
│                                                                          │
│  Alert + sync service (Python FastAPI)  → WhatsApp, local DB, cloud push │
└──────────────────────────────────────────────────────────────────────────┘
                                   │ events only (never video)
┌── CLOUD (optional SaaS) ─────────▼───────────────────────────────────────┐
│  FastAPI + TimescaleDB + Next.js dashboard                               │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why not rewrite everything in C++/Rust for speed?** Because it would be *slower to build*
for **near-zero runtime gain** — the GPU plugins already do 95% of the work, and your
rules are arithmetic on tiny metadata. Measured proof: our 50-camera xlarge run sat at
14–30% GPU with a Python probe doing the counting. The bottleneck is the **video decoder**,
which no language choice changes. Spend engineering effort on rules and product, not on
rewriting hot paths that aren't hot.

**When C++ *is* worth it:**
- The bbox parser (mandatory — runs inside `nvinfer`).
- A single rule that genuinely processes huge object counts with heavy geometry.
- Jetson/edge devices where you want to shave every millisecond.

### 5.4 Efficiency checklist (bigger wins than language)

1. **`interval`** — detect every Nth frame (2–3 fps is plenty for alerts). Biggest single
   lever on camera capacity.
2. **Substream resolution** — 704×576 instead of 1080p roughly doubles cameras (decoder is
   pixel-bound). Our #1 measured finding.
3. **Batch across cameras** (`nvstreammux batch-size`) — one GPU trip for many frames.
4. **FP16 engines** (`network-mode=2`) — ~2× faster than FP32, no accuracy loss for
   detection. INT8 (`=1`) is faster still if you calibrate.
5. **One shared model** where possible — each distinct engine costs VRAM; don't load 5
   models if 2 cover the fleet.
6. **Multi-decoder GPU** (4090/5090/L4) or **multiple boxes** past ~64× 720p cameras —
   the decoder, not compute, is the wall.

---

## 6. Quick decision guide

| You want to… | Do this |
|---|---|
| Stand up a pipeline for a new model fast | Ask the assistant → Inference Builder **MCP** generates config + skeleton |
| Run a capacity benchmark | `scripts/benchmark_deepstream.py` (config-only, no app code) |
| Build a real app (dwell, theft, PPE…) | Write a **Python `pyservicemaker`** pipeline + a **probe** with your rule |
| Make detection faster per camera | Raise `interval`, drop substream resolution, use FP16 |
| Run more cameras than one GPU allows | Multi-decoder GPU or split across boxes |
| Add a new custom model output format | Write/adjust the **C++ parser** (`nvdsinfer_*.cpp`) |
| Ship alerts / dashboard | **Python FastAPI** service consuming events off Redis/`nvmsgbroker` |

---

## 7. Summary

- The **DeepStream MCP (Inference Builder)** is an AI-callable code generator: it scaffolds
  correct pipelines, configs, Docker images, and serving code from a plain-English request
  or a small YAML. It bootstraps; it doesn't write your business logic.
- **Apps are built on metadata, not pixels.** Attach a **probe** after the tracker, read
  `{class, box, object_id}`, apply a rule, emit an event. Every app is the same 4 steps.
- **Best stack:** DeepStream GPU plugins do the heavy work; **C++** only for the bbox
  parser; **Python (`pyservicemaker`)** for pipeline + rules; **Python FastAPI** for
  alerts/dashboard. Rewriting in C++/Rust buys almost nothing because the GPU and the
  video **decoder** — not your code — set the ceiling.
