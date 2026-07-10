# NVIDIA DeepStream coding agent cookbook

Version: DeepStream 9.0 focused  
Purpose: give Claude Code, Codex, Cursor, or another coding agent enough structure to generate useful DeepStream apps without guessing.

This is a practical reference. It explains the DeepStream stack, what the major plug-ins do, which sample apps to copy from, and how to prompt an agent.

Sources are listed at the end.

---

# 1. DeepStream in plain English

DeepStream is NVIDIA’s real-time video AI pipeline SDK.

It is used when you want to process live camera feeds, video files, RTSP streams, images, audio, or sensor data and turn them into structured events.

Example:

```text
Camera stream
→ decode video
→ batch multiple streams
→ run AI model
→ track objects
→ draw boxes/counts
→ send event to dashboard/cloud/CRM
```

Good use cases:

- Smart CCTV
- People counting
- Vehicle tracking
- Warehouse monitoring
- Retail analytics
- Manufacturing defect detection
- Safety zone alerts
- Parking lot analytics
- Multi-camera tracking
- AI video search and summarization
- Edge camera appliances using Jetson
- GPU server video analytics using dGPU

Not ideal for:

- Normal websites
- Simple CRM automation
- Basic chatbots
- Text-only AI agents
- Light automations that do not need real-time video

---

# 2. Mental model for coding agents

A DeepStream app is a GStreamer pipeline.

Think of each plug-in as one block in a video factory line.

```text
source → decode → mux → preprocess → infer → track → analytics → display/message/save
```

Important GStreamer words:

- Element: one processing block, such as `nvinfer` or `nvtracker`
- Pipeline: connected elements
- Pad: input/output connection point on an element
- Buffer: video/audio/image data moving through the pipeline
- Metadata: AI results attached to buffers, such as bounding boxes, class IDs, object IDs, timestamps
- Sink: output target, such as display, file, message broker, or cloud endpoint
- Source: input target, such as RTSP camera, file, USB camera, UDP, appsrc

DeepStream’s value is that many heavy steps run on NVIDIA hardware:

- Video decode
- Video encode
- Image scaling
- Color conversion
- AI inference
- Tracking
- Pre/post-processing
- Multi-stream batching
- GPU memory operations

---

# 3. Recommended coding path in 2026

For new Python DeepStream work, prefer `pyservicemaker`.

Reason:

- NVIDIA’s current DeepStream Coding Agent skill targets DeepStream SDK 9.0 using Python `pyservicemaker`.
- DeepStream docs say traditional Python bindings are deprecated and recommend `pyservicemaker`.
- Service Maker hides a lot of raw GStreamer complexity.

Choose based on need:

## Use Flow API when

- You want fast prototypes
- You want common video AI workflows
- You do not need deep custom GStreamer control
- You want readable Python

## Use Pipeline API when

- You need more control
- You need custom elements
- You need custom metadata/probes
- You need to mirror old C/C++ DeepStream sample apps

## Use C/C++ when

- You need production-grade low-level control
- You need custom plugins
- You need maximum performance tuning
- You are extending DeepStream internals

## Avoid old Python bindings for new projects

Use only if you are maintaining older apps or need specific examples from `deepstream_python_apps`.

---

# 4. Agent skill setup

## Clone NVIDIA DeepStream Coding Agent

```bash
git clone https://github.com/NVIDIA-AI-IOT/DeepStream_Coding_Agent
```

The main DeepStream skill should be here:

```bash
DeepStream_Coding_Agent/skills/deepstream-dev/SKILL.md
```

Expected structure:

```bash
deepstream-dev/
  SKILL.md
  references/
    best_practices.md
    buffer_apis.md
    gstreamer_plugins.md
    kafka_messaging.md
    media_extractor_advanced.md
    nvinfer_config.md
    rest_api_dynamic.md
    service_maker_api.md
    tracker_config.md
    troubleshooting.md
    use_cases_pipelines.md
    utilities_config.md
    metamux_config.md
    docker_containers.md
```

## Claude Code setup

User-level install:

```bash
mkdir -p ~/.claude/skills
cp -r DeepStream_Coding_Agent/skills/deepstream-dev ~/.claude/skills/
```

Workspace-level install:

```bash
mkdir -p .claude/skills
cp -r DeepStream_Coding_Agent/skills/deepstream-dev .claude/skills/
```

Verify:

```text
Create a DeepStream pipeline that reads a video file and runs object detection using ResNet18 TrafficCamNet.
```

Claude should automatically load the `deepstream-dev` skill or allow manual invocation if your setup supports slash commands.

## Codex setup

OpenAI’s current Codex customization docs list global skills under:

```bash
$HOME/.agents/skills
```

Repo-level skills go under:

```bash
.agents/skills
```

Install globally:

```bash
mkdir -p ~/.agents/skills
cp -r DeepStream_Coding_Agent/skills/deepstream-dev ~/.agents/skills/
```

Install per project:

```bash
mkdir -p .agents/skills
cp -r DeepStream_Coding_Agent/skills/deepstream-dev .agents/skills/
```

NVIDIA’s DeepStream Coding Agent repository currently also mentions Codex examples using:

```bash
~/.codex/skills/deepstream-dev
```

Practical safe option:

```bash
mkdir -p ~/.agents/skills ~/.codex/skills
cp -r DeepStream_Coding_Agent/skills/deepstream-dev ~/.agents/skills/
cp -r DeepStream_Coding_Agent/skills/deepstream-dev ~/.codex/skills/
```

Then restart Codex.

## Cursor setup

User-level:

```bash
mkdir -p ~/.cursor/skills
cp -r DeepStream_Coding_Agent/skills/deepstream-dev ~/.cursor/skills/
```

Workspace-level:

```bash
mkdir -p .cursor/skills
cp -r DeepStream_Coding_Agent/skills/deepstream-dev .cursor/skills/
```

## Better update method using symlink

Instead of copying, symlink the skill folder.

Linux/macOS example:

```bash
mkdir -p ~/.claude/skills
ln -s /absolute/path/to/DeepStream_Coding_Agent/skills/deepstream-dev ~/.claude/skills/deepstream-dev
```

Update later:

```bash
cd /absolute/path/to/DeepStream_Coding_Agent
git pull
```

---

# 5. Core DeepStream pipeline patterns

## Pattern A: single video file object detection

```text
file/URI source
→ decode
→ nvstreammux
→ nvinfer
→ nvdsosd
→ renderer
```

Use when:

- You are learning DeepStream
- You want hello-world object detection
- You want bounding boxes on one video

Sample app to copy:

```text
deepstream-test1
```

Agent prompt:

```text
Use the deepstream-dev skill. Build a DeepStream 9.0 Python pyservicemaker app that reads one video file using nvurisrcbin, runs TrafficCamNet object detection through nvinfer, draws bounding boxes with nvdsosd, and renders the output. Save code in video_infer_app and include README.md.
```

## Pattern B: detection + tracking + classification

```text
source
→ decode
→ nvstreammux
→ nvinfer primary detector
→ nvtracker
→ nvinfer secondary classifier
→ nvdsosd
→ renderer
```

Use when:

- You need stable IDs across frames
- You need vehicle make/type or person attributes
- You need object-level history

Sample app to copy:

```text
deepstream-test2
```

## Pattern C: multiple RTSP cameras

```text
RTSP source 1
RTSP source 2
RTSP source N
→ decode each
→ nvstreammux batch
→ nvinfer
→ nvtracker
→ nvmultistreamtiler
→ nvdsosd
→ renderer
```

Use when:

- CCTV monitoring
- Multi-camera security
- Yard/warehouse tracking
- Retail cameras

Sample app to copy:

```text
deepstream-test3
```

## Pattern D: video analytics rules

```text
source
→ decode
→ nvstreammux
→ nvinfer
→ nvtracker
→ nvdsanalytics
→ nvdsosd
→ sink
```

Use when:

- Line crossing
- Region of interest filtering
- Direction detection
- Overcrowding
- People counting
- Vehicle entering/leaving zones

Sample app to copy:

```text
deepstream-nvdsanalytics-test
```

## Pattern E: cloud/event messaging

```text
source
→ decode
→ nvstreammux
→ nvinfer
→ nvtracker
→ metadata creation
→ nvmsgconv
→ nvmsgbroker
→ Kafka/Azure/MQTT/Redis/AMQP
```

Use when:

- You need events in a web dashboard
- You need alerts in backend
- You need camera detections in CRM
- You need Kafka/IoT stream output

Sample apps to copy:

```text
deepstream-test4
deepstream-test5
```

## Pattern F: smart record

```text
RTSP camera
→ detection/tracking
→ event trigger
→ smart record
→ save incident clip
```

Use when:

- Save only important clips
- Security incidents
- Restricted zone alerts
- Vehicle entry proof
- Safety violation evidence

Sample app to copy:

```text
deepstream-testsr
```

## Pattern G: 360-degree camera correction

```text
360 camera stream
→ dewarper
→ detection/tracking/display
```

Use when:

- Fisheye cameras
- Warehouses
- Retail ceilings
- Parking areas

Sample app to copy:

```text
deepstream-dewarper-test
```

## Pattern H: AI video summarization/VLM

```text
RTSP streams
→ decode
→ frame sampling
→ RGB conversion
→ media extractor
→ VLM backend
→ Kafka/API output
```

Use when:

- “What happened in this camera?”
- Visual AI agents
- Search/summarize long video
- Industrial video understanding

Agent prompt should mention:

- Do not mix frames from different streams in one batch
- Sample frames at a fixed interval
- Send summaries to Kafka or REST API
- Keep stream IDs attached to every summary

---

# 6. Plugin groups

This section explains the common DeepStream plug-ins in practical language.

## 6.1 Source/input plug-ins

### `nvurisrcbin`

Purpose:

- Reads URI sources such as video files or RTSP streams.
- Automatically handles many source/decode details.
- Good default source for coding agents.

Use for:

- Single file input
- RTSP input
- Agent-generated starter apps

Agent instruction:

```text
Prefer nvurisrcbin for file or RTSP input unless the task requires manual decodebin control.
```

### `nvmultiurisrcbin`

Purpose:

- Manages multiple URI sources.
- Useful for many RTSP/video sources.
- Supports dynamic source management through REST-style workflows in DeepStream server patterns.

Use for:

- Multi-camera systems
- Dynamic camera add/remove
- SaaS dashboard controlling cameras

### `nvdsdynamicsrcbin`

Purpose:

- Developer-preview dynamic source bin.
- Designed for runtime camera/source addition and removal.

Use for:

- Camera systems where sources change while app is running

Caution:

- Developer preview. Ask agent to check docs and version compatibility.

### `nvdsudpsrc` and `nvdsudpsink`

Purpose:

- UDP input/output for DeepStream data flow.

Use for:

- Network streaming
- Custom low-latency transfer
- Specialized distributed systems

### `nvunixfdsrc` and `nvunixfdsink`

Purpose:

- UNIX file descriptor based source/sink.
- Useful for process-to-process sharing.

Use for:

- IPC
- Advanced Linux pipeline sharing

### `appsrc` and `appsink`

Purpose:

- Standard GStreamer elements for pushing data from your own code into a pipeline or pulling data out into your own code.

Use for:

- Integrating non-DeepStream code
- Feeding CUDA frames
- Custom apps that already own the video frame lifecycle

Sample apps:

```text
deepstream-appsrc-test
deepstream-appsrc-cuda-test
```

---

## 6.2 Decode, encode, and image conversion plug-ins

### `Gst-nvvideo4linux2`

Purpose:

- NVIDIA-accelerated video decoder/encoder path.
- Uses NVIDIA hardware where available.

Use for:

- H.264/H.265 decode
- Hardware video encode
- High stream density

Agent instruction:

```text
For production RTSP/video pipelines, use NVIDIA accelerated decode/encode where possible instead of CPU software codecs.
```

### `nvvideoconvert`

Purpose:

- GPU-accelerated video format conversion.
- Converts color formats and memory types.

Use for:

- Before OSD
- Before sinks
- Before models needing a specific format
- Converting NV12/RGBA/RGB formats

### `nvjpegdec`

Purpose:

- JPEG decode.

Use for:

- JPEG camera/image workflows
- Image inferencing

### `nvimagedec`

Purpose:

- General image decode.

Use for:

- Image-based inference pipelines

### `nvjpegenc`

Purpose:

- JPEG encode.

Use for:

- Saving event snapshots
- Attaching encoded frames as metadata

### `nvimageenc`

Purpose:

- General image encode.

Use for:

- Image output workflows

---

## 6.3 Batching, demuxing, and display layout

### `nvstreammux`

Purpose:

- Combines frames from multiple sources into one batch.
- Helps the GPU process many cameras efficiently.
- Attaches batched metadata.

Use for:

- Almost every multi-stream DeepStream app
- Efficient inference

Key things to configure:

- `batch-size`
- Width and height
- Live source mode
- Timeout
- Memory type
- Number of sources

Agent instruction:

```text
Set nvstreammux batch-size equal to the number of active sources unless the design intentionally uses a different batching strategy.
```

### `nvstreamdemux`

Purpose:

- Splits a batched stream back into individual source streams.

Use for:

- Per-camera output branches
- Per-camera saving/display after shared inference
- Multi-output systems

Sample apps:

```text
deepstream-demuxer-static
deepstream-demuxer-dynamic
```

### `nvmultistreamtiler`

Purpose:

- Makes a grid view from multiple streams.

Use for:

- 2x2 camera wall
- 3x3 camera dashboard
- Operator monitoring display

### `nvdsmetamux`

Purpose:

- Merges metadata from multiple branches.

Use for:

- Complex pipelines with parallel inference branches
- Combining multiple model outputs
- Multi-stage AI graphs

---

## 6.4 Pre-processing, inference, and post-processing

### `nvdspreprocess`

Purpose:

- Prepares input for inference.
- Can operate on predefined regions of interest.
- Useful for resizing, normalization, cropping, tensor preparation, and ROI-based inference.

Use for:

- ROI inference
- Custom model input preprocessing
- Reducing compute by running inference only on selected zones

Sample app:

```text
deepstream-preprocess-test
```

Agent instruction:

```text
Use nvdspreprocess when the model needs non-default input transforms or ROI-specific processing before nvinfer.
```

### `nvinfer`

Purpose:

- Runs TensorRT inference.
- Used for primary detectors and secondary classifiers.
- Handles common detection/classification/segmentation model workflows.

Use for:

- Object detection
- Vehicle/person detection
- Classification
- Segmentation with supported parsers
- Primary and secondary inference

Common config items:

- Model engine path
- ONNX/ETLT model path
- Labels file
- Batch size
- Network mode FP32/FP16/INT8
- Input dimensions
- Class attributes
- Parser function
- Custom parser library
- Unique GIE ID
- Primary or secondary mode

Agent instruction:

```text
Use nvinfer for TensorRT-based local inference. Generate a separate nvinfer config file and keep model paths configurable.
```

### `nvinferserver`

Purpose:

- Runs inference using NVIDIA Triton Inference Server integration.
- Allows models from frameworks such as PyTorch/TensorFlow through Triton.
- Useful for remote or server-managed inference.

Use for:

- Triton model repository
- Ensembles
- Complex model serving
- Multi-framework inference
- Remote inference architectures

Agent instruction:

```text
Use nvinferserver when the task explicitly requires Triton, model ensembles, remote inference, or a Triton model repository. Otherwise prefer nvinfer for simpler local TensorRT inference.
```

### `nvdspostprocess`

Purpose:

- Customizable post-processing for tensor outputs from `nvinfer` or `nvinferserver`.
- Supports custom library interface for parsing outputs.

Use for:

- Custom detectors
- Custom classifiers
- Models whose output needs special parsing
- Cleaner separation of inference and post-processing

---

## 6.5 Tracking plug-ins and tracker types

### `nvtracker`

Purpose:

- Assigns persistent IDs to detected objects.
- Tracks objects across frames.
- Required for direction detection and line crossing style analytics.

Use for:

- Person tracking
- Vehicle tracking
- Object dwell time
- Line crossing
- Multi-camera handoff
- Reducing duplicate detections

Common low-level tracker options:

- IOU Tracker
- NvSORT
- NvDeepSORT
- NvDCF
- MaskTracker
- MV3DT or multiview tracking patterns in newer DeepStream workflows

Practical choice guide:

### IOU Tracker

Use when:

- You need simple tracking
- Objects are clear
- You want lightweight CPU/GPU overhead
- Accuracy demands are not high

Downside:

- Can lose IDs during occlusion
- Weak for crowded scenes

### NvSORT

Use when:

- You need a stronger simple tracker than IOU
- You care about motion prediction
- You still want relatively lightweight tracking

### NvDeepSORT

Use when:

- You need re-identification
- People/vehicles disappear and reappear
- You need stronger identity continuity

Downside:

- More compute and model setup

### NvDCF

Use when:

- You need robust tracking in video analytics
- You need better visual tracking
- You are doing people/vehicle counting in more realistic scenes

### MaskTracker

Use when:

- You are tracking segmentation masks
- You need object masks, not just boxes

Caution:

- Developer-preview style workflows may change.

Agent instruction:

```text
Use nvtracker after primary nvinfer if the task needs object IDs, line crossing, direction detection, dwell time, or stable event logic.
```

---

## 6.6 Analytics and visualization

### `nvdsanalytics`

Purpose:

- Rule-based analytics using metadata from `nvinfer` and `nvtracker`.

Supports:

- ROI filtering
- Overcrowding detection
- Direction detection
- Line crossing

Important:

- Direction detection and line crossing need tracker IDs because they require history.
- Rules are configured in a config file.
- Analytics output is attached as DeepStream user metadata.

Use for:

- Count people crossing a doorway
- Count vehicles entering a yard
- Detect people inside restricted zone
- Detect overcrowding
- Detect wrong-way movement

Sample app:

```text
deepstream-nvdsanalytics-test
```

Agent instruction:

```text
If the user asks for line crossing, wrong direction, ROI alerts, or overcrowding, include nvtracker before nvdsanalytics and generate an analytics config file.
```

### `nvdsosd`

Purpose:

- On-screen display.
- Draws bounding boxes, text, labels, masks, and other overlays.

Use for:

- Visual debugging
- Demo output
- Operator monitor
- Annotated video file output

### `nvsegvisual`

Purpose:

- Visualizes segmentation output.

Use for:

- Semantic segmentation
- Instance segmentation display

### `nvof`

Purpose:

- Optical flow plug-in.
- Produces motion vector metadata.

Use for:

- Motion analysis
- Flow-based analytics
- Advanced video understanding

### `nvofvisual`

Purpose:

- Visualizes optical flow motion vectors.

Use for:

- Debugging optical flow
- Demo visuals

Sample app:

```text
deepstream-nvof-test
```

### `nvdewarper`

Purpose:

- Corrects fisheye/360-degree camera views.
- Uses calibration parameters.

Use for:

- 360 cameras
- Ceiling cameras
- Fisheye lenses
- Retail/warehouse aisle views

Sample app:

```text
deepstream-dewarper-test
```

---

## 6.7 Messaging, cloud, and event output

### `nvmsgconv`

Purpose:

- Converts DeepStream metadata into a message schema/payload.
- Commonly creates JSON event payloads.

Use for:

- Sending detections to backend
- Creating structured events
- Converting object metadata into cloud messages

### `nvmsgbroker`

Purpose:

- Sends payloads to a server/message system using protocol adapters.

Supported adapter families listed in NVIDIA docs include:

- Kafka
- Azure IoT/MQTT
- AMQP
- Redis
- MQTT

Use for:

- Kafka event stream
- IoT dashboard
- Cloud analytics
- Real-time backend alerts
- CRM or database ingestion through your own consumer

Agent instruction:

```text
For cloud/dashboard output, create event metadata, pass it to nvmsgconv, then send through nvmsgbroker. Keep protocol adapter config separate from app code.
```

Practical backend pattern:

```text
DeepStream detection event
→ nvmsgconv JSON
→ nvmsgbroker Kafka topic
→ backend consumer
→ database/dashboard/SMS alert
```

---

## 6.8 3D, lidar, sensor fusion

### `nvds3dfilter`

Purpose:

- 3D data filter framework for DeepStream DS3D.
- Used in point cloud/depth/lidar pipelines.

Use for:

- Lidar-camera fusion
- Depth cameras
- 3D detection
- Point cloud processing

### `nvds3dbridge`

Purpose:

- Bridges data between DeepStream 3D components.

Use for:

- Video and 3D data interop

### `nvds3dmixer`

Purpose:

- Mixes multisensor 3D data.

Use for:

- Multi-camera + lidar fusion
- Multisensor alignment workflows

Sample apps:

```text
deepstream-3d-lidar-sensor-fusion
deepstream-3d-depth-camera
deepstream-lidar-inference-app
```

---

## 6.9 Multi-GPU and distributed pipeline plug-ins

### `nvdsucx`

Purpose:

- Communication plug-in using UCX.
- Helps transfer data in advanced distributed or multi-process setups.

Use for:

- High-performance GPU communication
- Advanced distributed DeepStream pipelines

Sample app:

```text
deepstream-ucx-test
```

### `nvdsxfer`

Purpose:

- Transfers DeepStream data across GPUs.
- Useful for multi-GPU/NVLink style scaling.

Use for:

- Multi-GPU pipelines
- Splitting processing across GPUs
- High stream density

Sample app:

```text
deepstream-multigpu-nvlink-test
```

---

## 6.10 Customization templates

### `dsexample`

Purpose:

- Template plug-in for integrating custom algorithms into a DeepStream graph.

Use for:

- Custom computer vision logic
- Custom frame processing
- Custom OpenCV/CUDA logic

### `nvdsvideotemplate`

Purpose:

- Template plug-in for custom video algorithms.

Use for:

- Non-GStreamer custom video algorithms
- Custom GPU/CUDA video processing

### `nvdsaudiotemplate`

Purpose:

- Template plug-in for custom audio processing.

Use for:

- Audio analytics
- Audio AI workflows

### `nvdsinfer_customparser`

Purpose:

- Custom parser library examples for model outputs.

Use for:

- YOLO-like model outputs
- Custom object detectors
- Custom classifiers
- Non-standard tensor output formats

Agent instruction:

```text
If a model output is not directly supported by nvinfer, generate or reference a custom parser library and document build steps.
```

---

# 7. Sample app map

Use this when asking your coding agent what to copy from.

## `deepstream-test1`

What it teaches:

- Single H.264/video pipeline
- Decode
- `nvstreammux`
- Primary inference with `nvinfer` or `nvinferserver`
- `nvdsosd`
- Renderer

Use when:

- Beginner object detection app

## `deepstream-test2`

What it teaches:

- Primary detector
- Tracker
- Secondary classifiers
- OSD

Use when:

- Detection + tracking + classification

## `deepstream-test3`

What it teaches:

- Multiple sources
- `uridecodebin`
- Batched inference through `nvstreammux`
- Stream metadata extraction

Use when:

- Multiple camera/RTSP app

## `deepstream-test4`

What it teaches:

- `nvmsgconv`
- `nvmsgbroker`
- Event metadata creation
- Vehicle/person event messages
- Custom copy/free functions for extended metadata

Use when:

- Single-stream detection events to backend/cloud

## `deepstream-test5`

What it teaches:

- Multi-stream messaging
- Configuring `nvmsgbroker` as sink
- Kafka/Azure style output
- RTCP sender report timestamp handling

Use when:

- Real CCTV system with cloud events

## `deepstream-app`

What it teaches:

- Full reference app
- Config-driven DeepStream app
- Primary and secondary inference
- Tracking
- Messaging
- Tiling
- OSD

Use when:

- Production-style config-driven app

## `deepstream-3d-lidar-sensor-fusion`

What it teaches:

- Multi-modal sensor fusion
- 6 cameras + lidar style BEVFusion pipeline
- 3D detection

Use when:

- Camera + lidar projects

## `deepstream-dewarper-test`

What it teaches:

- Dewarp 360-degree camera streams
- Read calibration from CSV
- Render dewarped views

Use when:

- Fisheye/360 camera projects

## `deepstream-nvof-test`

What it teaches:

- Optical flow
- Motion vector metadata
- Optical flow visualization

Use when:

- Motion analysis

## `deepstream-user-metadata-test`

What it teaches:

- Add custom metadata
- Retrieve metadata later in pipeline

Use when:

- You need custom fields attached to frames/objects

## `deepstream-image-decode-test`

What it teaches:

- MJPEG/JPEG/image decoding
- Image inference instead of video

Use when:

- Image streams or JPEG camera input

## `deepstream-gst-metadata-test`

What it teaches:

- Add metadata before `nvstreammux`
- Access it after `nvstreammux`

Use when:

- You need source metadata preserved through batching

## `deepstream-infer-tensor-meta-app`

What it teaches:

- Access raw tensor output from `nvinfer` as metadata

Use when:

- You need custom tensor parsing downstream

## `deepstream-preprocess-test`

What it teaches:

- ROI preprocessing before inference

Use when:

- Only infer on regions
- Model needs special preprocessing

## `deepstream-3d-action-recognition`

What it teaches:

- Sequence batching
- 2D/3D action recognition model inference
- Temporal batching

Use when:

- Detect actions/events over time, not just objects

## `deepstream-nvdsanalytics-test`

What it teaches:

- ROI filtering
- Line crossing
- Direction detection
- Overcrowding

Use when:

- Counting and rule-based analytics

## `deepstream-opencv-test`

What it teaches:

- OpenCV inside DeepStream via `dsexample`

Use when:

- Custom CV logic

Caution:

- OpenCV support may require compile flags and package setup.

## `deepstream-image-meta-test`

What it teaches:

- Attach encoded image as metadata
- Save JPEG snapshots

Use when:

- Event snapshots
- Evidence capture

## `deepstream-appsrc-test`

What it teaches:

- AppSrc/AppSink usage
- Consume/emit data from non-DeepStream code

Use when:

- Your application owns input/output frames

## `deepstream-appsrc-cuda-test`

What it teaches:

- Feed CUDA frames from outside DeepStream into a pipeline

Use when:

- CUDA interop

## `deepstream-transfer-learning-app`

What it teaches:

- Save low-confidence object images for later training

Use when:

- Active learning
- Dataset improvement

## `deepstream-testsr`

What it teaches:

- Event-based smart recording

Use when:

- Save clips only around events

## `deepstream-avsync-app`

What it teaches:

- Audio/video/text sync
- ASR output sync patterns

Use when:

- Multimodal audio/video timing

Caution:

- Some speech workflows require NVIDIA Riva.

## `deepstream-nmos`

What it teaches:

- DeepStream as NMOS node
- Network media orchestration
- AMWA IS-04/IS-05 style workflows

Use when:

- Broadcast/media network systems

## `deepstream-ucx-test`

What it teaches:

- `gst-nvdsucx`
- Communication between DeepStream components

Use when:

- Advanced distributed transfer

## `deepstream-3d-depth-camera`

What it teaches:

- Depth capture
- Point cloud processing
- 3D point rendering

Use when:

- Depth cameras

## `deepstream-lidar-inference-app`

What it teaches:

- Read point cloud data
- Triton inference
- PointPillars 3D object detection
- Render point cloud and 3D objects

Use when:

- Lidar-only or lidar-heavy systems

## `deepstream-server`

What it teaches:

- REST API control of DeepStream pipeline at runtime

Use when:

- SaaS control panel
- Add/remove streams
- Change parameters while running

## `deepstream-can-orientation-app`

What it teaches:

- Can orientation detection
- VPI template matching
- Video template plugin

Use when:

- Manufacturing quality inspection

## `TritonBackendEnsemble`

What it teaches:

- Triton ensemble models
- Custom Triton C++ backend
- Access DeepStream metadata in Triton workflows

Use when:

- Complex model serving

## `deepstream-multigpu-nvlink-test`

What it teaches:

- `nvdsxfer`
- Multi-GPU data transfer
- NVLink style scaling simulation

Use when:

- Large stream count
- Multiple GPUs

## `deepstream-ipc-test-app`

What it teaches:

- Decoder buffer sharing on Jetson
- Separate pipelines in different processes
- Optimize NVDEC hardware usage

Use when:

- Jetson process isolation
- Shared decode optimization

## `deepstream-demuxer-static`

What it teaches:

- Static demux branches
- `nvstreamdemux` separation after batching
- Dynamic source pad handling

Use when:

- Split batched stream into per-camera branches

## `deepstream-demuxer-dynamic`

What it teaches:

- Runtime demuxer creation
- Tee branch to tiler and demuxer
- Per-demux branch creation

Use when:

- Dynamic per-stream outputs

---

# 8. Metadata cookbook

DeepStream apps pass both video buffers and metadata.

Important metadata objects:

## `NvDsBatchMeta`

Represents metadata for a batch of frames.

Use when:

- Iterating over all frames in a batched buffer
- Accessing source/frame lists

## `NvDsFrameMeta`

Represents metadata for one frame from one source.

Contains:

- Source ID
- Frame number
- Timestamp
- Object list
- Frame-level user metadata

Use when:

- Per-camera events
- Per-frame counts
- Source-specific logic

## `NvDsObjectMeta`

Represents one detected/tracked object.

Contains:

- Class ID
- Object ID
- Confidence
- Bounding box
- Text params
- Classifier metadata
- User metadata

Use when:

- Count objects
- Create alerts
- Draw custom labels
- Attach business metadata

## `NvDsClassifierMeta`

Represents classifier output attached to an object.

Use when:

- Vehicle make/type
- Color classifier
- Person attributes

## `NvDsUserMeta`

Custom metadata attached to frame/object/batch.

Use when:

- Add business-specific fields
- Attach analytics results
- Store custom events

## `NvDsEventMsgMeta`

Event message metadata for `nvmsgconv`.

Use when:

- Sending events to Kafka/Azure/MQTT/etc.
- Vehicle/person event schema
- Cloud alerts

## `NvDsAnalyticsFrameMeta`

Frame-level analytics metadata from `nvdsanalytics`.

Use when:

- Total count
- Overcrowding status
- ROI counts

## `NvDsAnalyticsObjInfo`

Object-level analytics metadata from `nvdsanalytics`.

Use when:

- This object crossed line
- This object moved wrong direction
- This object belongs to ROI

Agent instruction:

```text
When creating event output, keep source_id, frame_num, timestamp, object_id, class_id, confidence, bbox, and any analytics labels in the payload.
```

---

# 9. Config files the agent should generate

## `nvinfer` config

Purpose:

- Defines model and inference behavior.

Common sections/fields:

```ini
[property]
gpu-id=0
net-scale-factor=1.0
model-engine-file=...
onnx-file=...
labelfile-path=...
batch-size=...
network-mode=2
num-detected-classes=...
gie-unique-id=1
process-mode=1
network-type=0
cluster-mode=2
```

Notes:

- `network-mode=2` usually means FP16 in many DeepStream configs.
- `process-mode=1` is primary inference.
- `process-mode=2` is secondary inference.
- `gie-unique-id` must be unique per inference element.
- Custom models may need a custom parser `.so`.

## `tracker` config

Purpose:

- Defines low-level tracking behavior.

Common choices:

```ini
ll-lib-file=/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so
ll-config-file=tracker_config.yml
tracker-width=...
tracker-height=...
gpu-id=0
```

Agent instruction:

```text
Use NvDCF or NvDeepSORT for more realistic people/vehicle tracking. Use IOU/NvSORT only for simple demos or low compute.
```

## `nvdsanalytics` config

Purpose:

- Defines ROI, line crossing, direction, and overcrowding rules.

Example concepts:

```ini
[property]
enable=1
config-width=1920
config-height=1080

[line-crossing-stream-0]
line-crossing-Exit=...
line-crossing-Entry=...

[roi-filtering-stream-0]
roi-Entrance=...

[overcrowding-stream-0]
roi-CrowdZone=...
object-threshold=...
```

Agent instruction:

```text
Ask user for camera resolution and draw coordinates, or create placeholder coordinates and clearly mark them for calibration.
```

## `nvmsgbroker` config

Purpose:

- Defines message broker settings.

Common targets:

- Kafka
- Azure IoT
- MQTT
- AMQP
- Redis

Agent instruction:

```text
Keep broker connection settings in config files or environment variables. Do not hardcode credentials.
```

## Source list YAML

Purpose:

- Defines multiple sources for Service Maker/Flow style apps.

Use when:

- Multiple RTSP cameras
- Cleaner deployment configs
- Dynamic source management

Agent instruction:

```text
Put RTSP URLs and camera names in a separate YAML config. Support environment variables for credentials.
```

---

# 10. Common business recipes

## Recipe 1: contractor yard vehicle entry monitor

Goal:

Detect trucks entering/leaving a yard and send events to a dashboard.

Pipeline:

```text
RTSP camera(s)
→ nvstreammux
→ nvinfer vehicle detector
→ nvtracker
→ nvdsanalytics line crossing
→ nvmsgconv
→ nvmsgbroker Kafka/MQTT
→ backend dashboard
```

Events:

```json
{
  "event_type": "vehicle_entry",
  "camera_id": "yard_gate_1",
  "object_id": 42,
  "class": "truck",
  "direction": "entry",
  "timestamp": "...",
  "confidence": 0.91
}
```

Agent prompt:

```text
Use the deepstream-dev skill. Build a DeepStream 9.0 Python pyservicemaker app for 2 RTSP cameras at a contractor yard. Detect vehicles with nvinfer, track with nvtracker, count gate entry/exit using nvdsanalytics line crossing, and send JSON events to Kafka using nvmsgconv and nvmsgbroker. Put source URLs, analytics coordinates, model paths, and Kafka settings in config files. Save in yard_vehicle_monitor.
```

## Recipe 2: warehouse restricted-zone person alert

Goal:

Alert if a person enters a restricted area.

Pipeline:

```text
RTSP
→ nvinfer person detector
→ nvtracker
→ nvdsanalytics ROI filtering
→ event payload
→ MQTT/SMS/backend
```

Agent prompt:

```text
Create a DeepStream app that monitors 4 RTSP warehouse cameras, detects people, tracks objects, checks restricted ROI zones using nvdsanalytics, and sends an MQTT alert when a person enters any restricted zone. Include placeholder ROI config and README instructions for calibration.
```

## Recipe 3: retail people counting

Goal:

Count people entering/exiting a store.

Pipeline:

```text
Entrance camera
→ person detector
→ tracker
→ line crossing
→ counts dashboard
```

Output:

- Entry count
- Exit count
- Net occupancy
- Per-hour totals

Agent prompt:

```text
Build a DeepStream people-counting app for one RTSP entrance camera. Use nvinfer person detection, nvtracker, nvdsanalytics line crossing, and output counts every 10 seconds as JSON logs. Also draw line-crossing status with nvdsosd.
```

## Recipe 4: manufacturing defect inspection

Goal:

Detect bad parts or orientation issues.

Pipeline:

```text
industrial camera/image source
→ preprocess ROI
→ defect detector/classifier
→ event snapshot
→ save/send report
```

Useful plugins:

- `nvdspreprocess`
- `nvinfer`
- `nvjpegenc`
- `nvmsgbroker`
- `nvdsvideotemplate` for custom logic

Agent prompt:

```text
Create a DeepStream inspection app that reads an industrial camera stream, crops the product ROI using nvdspreprocess, runs a custom ONNX defect detector with nvinfer, saves JPEG snapshots of failed detections, and sends JSON events to a REST/Kafka-compatible output module.
```

## Recipe 5: smart CCTV incident clip recorder

Goal:

Record clips only when something happens.

Pipeline:

```text
RTSP
→ detection
→ tracking
→ event rule
→ smart record
→ save clip
```

Sample to copy:

```text
deepstream-testsr
```

Agent prompt:

```text
Build a DeepStream smart record app for RTSP cameras. Trigger recording when a person enters a restricted ROI. Save 10 seconds before and 20 seconds after the event. Include configurable output folder and event JSON log.
```

## Recipe 6: parking occupancy

Goal:

Count vehicles and parking occupancy.

Pipeline:

```text
parking cameras
→ vehicle detector
→ tracker
→ ROI zones
→ occupancy state
→ dashboard events
```

Agent prompt:

```text
Create a DeepStream parking occupancy app for 6 RTSP cameras. Detect cars/trucks, track them, map detections to parking-zone ROIs, maintain occupancy counts per zone, and publish updates to Kafka every 5 seconds.
```

---

# 11. Agent prompt library

## Prompt: inspect installed DeepStream

```text
Use the deepstream-dev skill. Inspect this machine for DeepStream SDK installation, GPU availability, CUDA/TensorRT versions, GStreamer plugin availability, and whether pyservicemaker is importable. Produce a short report and do not modify files.
```

## Prompt: create starter app

```text
Use the deepstream-dev skill. Create a DeepStream 9.0 Python pyservicemaker starter app that reads one video file, runs TrafficCamNet object detection, draws bounding boxes, and displays the result. Save in video_infer_app. Include README.md, requirements if needed, and exact run commands.
```

## Prompt: convert sample app to project

```text
Use the deepstream-dev skill. Use deepstream-test3 as the reference pattern and create a clean Python pyservicemaker project for 4 RTSP cameras. The app should batch streams, run inference, tile video in 2x2, draw boxes, and support source URLs from config.yaml.
```

## Prompt: add tracking

```text
Use the deepstream-dev skill. Add nvtracker after primary inference. Use a tracker config file. Preserve object IDs in all event outputs and display object IDs in OSD labels.
```

## Prompt: add line crossing

```text
Use the deepstream-dev skill. Add nvdsanalytics after nvtracker for line crossing. Generate a config file with placeholder coordinates for stream 0 and explain how to calibrate the coordinates from the camera resolution.
```

## Prompt: add Kafka events

```text
Use the deepstream-dev skill. Add event output using nvmsgconv and nvmsgbroker. Publish JSON events to Kafka. Keep broker address, topic, and credentials in config or env vars. Include a sample Kafka consumer script for testing.
```

## Prompt: debug pipeline error

```text
Use the deepstream-dev skill and troubleshooting reference. Diagnose this DeepStream error log. Explain the likely root cause, the exact file/config line to check, and the smallest fix. Do not rewrite the whole app unless needed.

ERROR LOG:
[paste full log here]
```

## Prompt: make it production-ready

```text
Use the deepstream-dev skill. Review this DeepStream app for production readiness. Check config separation, error handling, RTSP reconnect behavior, GPU selection, batch-size correctness, tracker config, model path handling, logging, Docker run instructions, and clean shutdown.
```

## Prompt: create Docker setup

```text
Use the deepstream-dev skill. Create a Dockerfile or docker-compose setup to run this DeepStream app inside the correct NVIDIA DeepStream container. Include GPU runtime flags, volume mounts for models/configs/videos, and README run commands.
```

## Prompt: agent must not guess

```text
Use the deepstream-dev skill. Before writing code, read the relevant files in references/. Do not invent DeepStream API names. If an API or property is uncertain, search the installed docs or inspect the plugin using gst-inspect-1.0.
```

---

# 12. Guardrails for coding agents

Add this to your project `AGENTS.md`, `CLAUDE.md`, or first prompt.

```text
DeepStream development rules:

1. Use the deepstream-dev skill before writing DeepStream code.
2. Prefer Python pyservicemaker for new apps.
3. Do not invent plugin properties. Verify with docs or gst-inspect-1.0.
4. Keep model paths, RTSP URLs, Kafka/MQTT settings, tracker config, and analytics coordinates in config files.
5. Never hardcode camera passwords or broker credentials.
6. Use nvurisrcbin for simple URI/file/RTSP sources unless the task needs manual source handling.
7. Use nvstreammux for multi-source batching.
8. If line crossing, direction detection, dwell time, or object IDs are needed, include nvtracker before nvdsanalytics.
9. Use nvmsgconv + nvmsgbroker for cloud/backend events.
10. Include README run instructions for bare metal and Docker where possible.
11. For custom models, document parser requirements and engine generation steps.
12. For generated code, include a minimal test path using NVIDIA sample video if available.
13. If DeepStream SDK is not installed, generate code only and clearly state runtime requirements.
```

---

# 13. Troubleshooting checklist

## Problem: pipeline does not start

Check:

- DeepStream SDK installed
- Correct container image
- NVIDIA runtime available
- GPU visible with `nvidia-smi`
- GStreamer can find DeepStream plugins
- Model path exists
- Config file paths are correct
- RTSP URL reachable

Useful commands:

```bash
gst-inspect-1.0 nvinfer
gst-inspect-1.0 nvstreammux
gst-inspect-1.0 nvtracker
gst-inspect-1.0 nvdsanalytics
gst-inspect-1.0 nvmsgbroker
```

## Problem: no detections

Check:

- Correct model file
- Correct labels file
- Correct input dimensions
- Correct parser
- Confidence threshold too high
- Wrong color format
- Incorrect preprocessing
- Batch size mismatch
- Engine file incompatible with GPU/TensorRT version

## Problem: tracker IDs keep changing

Check:

- Detector confidence too low
- Tracker choice too simple
- Tracker config too aggressive
- Frame rate too low
- Occlusion/crowding
- Objects too small
- Wrong tracker resolution
- Need NvDCF/NvDeepSORT instead of IOU

## Problem: line crossing not working

Check:

- `nvtracker` is before `nvdsanalytics`
- Object has tracker ID
- Line coordinates match actual video resolution
- Correct stream ID in analytics config
- Direction vector is correct
- Object class filtering is correct
- Bottom-center point of bbox crosses the line

## Problem: Kafka/MQTT events not arriving

Check:

- `nvmsgconv` before `nvmsgbroker`
- Event metadata is attached
- Broker connection string
- Topic name
- Protocol adapter library
- Firewall/network
- Broker credentials
- Consumer group/topic exists
- Payload schema

## Problem: high latency

Check:

- Too many streams per GPU
- Batch timeout too high
- Source buffering
- RTSP latency settings
- Heavy tracker
- Model too large
- CPU decode accidentally used
- Display sink slowing pipeline
- Disk writing on every frame

## Problem: poor stream density

Check:

- Use hardware decode
- Use batching
- Use FP16/INT8 if acceptable
- Lower resolution
- Lower FPS
- Use lighter model
- Avoid unnecessary OSD/rendering in headless mode
- Use tiler only for display
- Avoid copying frames CPU-side

---

# 14. Docker/runtime notes

To generate code, you do not need an NVIDIA GPU.

To run DeepStream code, you usually need:

- NVIDIA GPU or Jetson
- NVIDIA driver
- CUDA-compatible runtime
- DeepStream SDK
- GStreamer dependencies
- TensorRT
- Model files/configs
- Correct container for platform

Common dGPU container pattern:

```bash
docker run -it --rm --runtime=nvidia --gpus all --network=host \
  -v $(pwd):/app -w /app \
  nvcr.io/nvidia/deepstream:9.0-triton-multiarch
```

Inside container:

```bash
python3 app.py
```

Use SBSA/DGX Spark style container only if targeting that platform.

---

# 15. How to structure a generated project

Recommended project layout:

```text
my_deepstream_app/
  README.md
  app.py
  configs/
    sources.yaml
    infer_primary.txt
    tracker_config.yml
    analytics_config.txt
    msgbroker_config.txt
  models/
    README.md
  scripts/
    check_env.sh
    run_docker.sh
    test_kafka_consumer.py
  logs/
    .gitkeep
```

README should include:

- What the app does
- Required hardware
- Required DeepStream version
- Model download/setup
- Config files
- Run command
- Docker command
- Expected output
- Troubleshooting

---

# 16. Good output requirements for coding agents

When your coding agent generates a DeepStream app, ask it to include:

- Clean app structure
- Config files
- README
- Docker/run instructions
- `gst-inspect` checks if possible
- Environment check script
- Sample source config
- No hardcoded credentials
- Clear comments around model paths
- Known limitations
- Exact plugin chain
- Expected pipeline diagram
- Debug mode/logging flag

---

# 17. Recommended first learning order

1. Run or generate `deepstream-test1` style app
2. Add `nvtracker`
3. Add multi-source batching
4. Add `nvmultistreamtiler`
5. Add `nvdsanalytics`
6. Add `nvmsgconv` and `nvmsgbroker`
7. Add smart record
8. Add custom model/parser
9. Add REST/dynamic source control
10. Scale to multi-GPU or multi-node only after the simple version works

---

# 18. Official resources

## NVIDIA DeepStream main page

Use for:

- Product overview
- Benefits
- High-level capabilities
- Performance table
- Current marketing claims

URL:

```text
https://developer.nvidia.com/deepstream-sdk
```

## NVIDIA DeepStream documentation overview

Use for:

- Current SDK version overview
- Supported platforms
- Architecture
- Python and C/C++ paths

URL:

```text
https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_Overview.html
```

## GStreamer plugin overview

Use for:

- Full plugin index
- Plugin-specific docs
- Metadata documentation
- Plugin properties

URL:

```text
https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_plugin_Intro.html
```

## DeepStream reference application

Use for:

- Main DeepStream app architecture
- Core plug-in graph
- Config-driven app structure

URL:

```text
https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_ref_app_deepstream.html
```

## C/C++ sample apps

Use for:

- Official sample app map
- Paths inside `/opt/nvidia/deepstream/deepstream/sources`
- Sample descriptions

URL:

```text
https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_C_Sample_Apps.html
```

## Python sample apps and bindings

Use for:

- Legacy Python sample app info
- Metadata access notes
- Python binding caveats

URL:

```text
https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_Python_Sample_Apps.html
```

## Service Maker for Python

Use for:

- Recommended Python path
- Flow API
- Pipeline API
- pyservicemaker install/runtime info

URL:

```text
https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_service_maker_python.html
```

## Service Maker overview

Use for:

- Why Service Maker exists
- C++ and Python abstraction layer
- Flow/Pipeline API mental model

URL:

```text
https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_service_maker_intro.html
```

## DeepStream Coding Agent repository

Use for:

- `deepstream-dev` skill
- Example prompts
- Skill installation
- Agent-assisted app generation

URL:

```text
https://github.com/NVIDIA-AI-IOT/DeepStream_Coding_Agent
```

## DeepStream Python apps repository

Use for:

- Legacy Python examples
- Metadata examples
- Python binding source/build notes

URL:

```text
https://github.com/NVIDIA-AI-IOT/deepstream_python_apps
```

## Codex skills documentation

Use for:

- Codex skill structure
- `SKILL.md`
- Global/repo-level skills path
- Progressive disclosure

URL:

```text
https://developers.openai.com/codex/skills
```

## Codex customization docs

Use for:

- `AGENTS.md`
- Skill path
- Repo-level instructions

URL:

```text
https://developers.openai.com/codex/concepts/customization
```

## Claude Code skills documentation

Use for:

- Claude Code `SKILL.md`
- Skill folders
- Personal/project skills
- Frontmatter
- Supporting files

URL:

```text
https://code.claude.com/docs/en/skills
```

## Claude Agent Skills overview

Use for:

- General skill format
- Claude Code filesystem-based custom skills
- Claude.ai/API skill differences

URL:

```text
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
```

---

# 19. One master prompt for your coding agent

Paste this into Claude Code, Codex, or Cursor after installing the skill.

```text
Use the deepstream-dev skill.

I am building production-style NVIDIA DeepStream 9.0 applications. Before generating code, consult the skill references, especially gstreamer_plugins.md, service_maker_api.md, nvinfer_config.md, tracker_config.md, kafka_messaging.md, rest_api_dynamic.md, troubleshooting.md, and docker_containers.md.

Rules:
- Prefer Python pyservicemaker for new apps.
- Do not invent API names or plugin properties.
- If uncertain, verify using docs or gst-inspect-1.0.
- Keep camera URLs, model paths, tracker config, analytics coordinates, and broker settings in config files.
- Do not hardcode secrets.
- Include README and run instructions.
- Include Docker instructions if runtime environment is unclear.
- For line crossing/direction/ROI analytics, use nvtracker before nvdsanalytics.
- For event output, use nvmsgconv and nvmsgbroker.
- Preserve source_id, frame_num, timestamp, object_id, class_id, confidence, bbox, and analytics labels in event payloads.

Task:
[write your DeepStream app requirement here]
```

---

# 20. Fast cheat sheet

Use this when you forget which plugin does what.

```text
nvurisrcbin          Read file/RTSP URI source
nvmultiurisrcbin     Manage many URI sources
nvstreammux          Batch multiple streams
nvstreamdemux        Split batched stream back out
nvdspreprocess       Preprocess frames/ROIs before inference
nvinfer              TensorRT inference
nvinferserver        Triton inference
nvdspostprocess      Custom postprocess tensor outputs
nvtracker            Track objects and assign IDs
nvdsanalytics        ROI, overcrowding, direction, line crossing
nvmultistreamtiler   Grid display for many streams
nvdsosd              Draw boxes/text/labels
nvvideoconvert       GPU video format conversion
nvvideo4linux2       NVIDIA video decode/encode
nvdewarper           Fisheye/360 camera correction
nvof                 Optical flow
nvofvisual           Optical flow visualization
nvsegvisual          Segmentation visualization
nvmsgconv            Convert metadata to message payload
nvmsgbroker          Send payload to Kafka/Azure/MQTT/AMQP/Redis
nvdsmetamux          Merge metadata from branches
nvds3dfilter         3D/lidar/depth filtering
nvds3dbridge         Bridge 3D/video data
nvds3dmixer          Mix multisensor 3D data
nvdsucx              UCX communication
nvdsxfer             Multi-GPU transfer
dsexample            Custom algorithm template
nvdsvideotemplate    Custom video plugin template
nvdsaudiotemplate    Custom audio plugin template
```
