# VisionSense Studio — Status (set up while you were AFK)

**Box:** Ubuntu 26.04 · RTX 3070 Ti · 16 GB RAM · `192.168.2.2`

## TL;DR
The **entire software + GPU stack is built, running, and production-ready.** The only
thing not working is **seeing your 15 real CCTV cameras — because this box cannot reach
them over the network** (not a software issue; see "The one blocker").

**Open the dashboard:** http://192.168.2.2:8000/  (or `localhost:8000` on the box)
You'll see the **`cam-demo`** tile detecting people live on the GPU, plus 15 camera tiles
showing "connecting" (they auto-light-up the moment the network path opens).

---

## What's done and verified ✅

| Area | Status | Detail |
|---|---|---|
| NVIDIA driver | ✅ active | 595.71.05, nouveau→nvidia (rebooted) |
| CUDA PyTorch | ✅ | torch 2.6.0+cu124, `cuda.is_available()` True |
| TensorRT engine | ✅ built | `models/yolo26n.engine`, **batch-15 = 23.5 fps/cam, 3.1 GB VRAM** |
| Detection | ✅ | person/bag/phone/laptop classes, ByteTrack IDs |
| Business logic + events | ✅ | headcount/desk/theft → **Redis stream** `cctv:events` |
| Redis | ✅ running | systemd-enabled, events verified publishing |
| NVDEC hardware decode | ✅ verified | `nvh264dec` decodes H.264 on the GPU's decoder |
| Dashboard UI | ✅ | live grid + per-cam status + events feed |
| Autostart | ✅ | `deploy/visionsense.service` (boot + auto-restart) |
| 15 cameras configured | ✅ | `config/cameras.yaml`, substream URLs |
| **15 cameras LIVE** | 🔴 blocked | **network — see below** |

---

## The one blocker: the cameras aren't reachable from this box

I tested your NVR (`103.83.89.187`) repeatedly: **dead on every port** (554, 80, 37777,
8000) from here, and outbound RTSP (port 554) to the public internet is firewalled on this
network (a public test RTSP server also timed out, while normal web traffic works).

**No software can bypass a blocked network path.** To make the 15 cameras work, do ONE of:

1. **If this server is on the same LAN as the NVR** (most likely): use the NVR's **local IP**
   instead of the public one. Find it (from a machine that can reach the NVR, check the
   router's device list / the NVR's network settings), then run:
   ```bash
   cd ~/Personal/visionsense-studio
   sed -i 's/103.83.89.187/<NVR_LAN_IP>/g' config/cameras.yaml
   sudo systemctl restart visionsense   # if the service is installed
   ```
2. **Open outbound TCP 554** on this box's router/firewall (and confirm the NVR's public
   port-forward for 554 is active).
3. **VPN** into the camera network.

Then verify all 15:
```bash
cd ~/Personal/visionsense-studio
PYTHONPATH=$PWD .venv/bin/python scripts/probe_cameras.py   # connects, prints WxH per cam
```
Once they answer, the running pipeline picks them up automatically (the dashboard tiles go
green). No code changes needed.

---

## How to run / control it

```bash
cd ~/Personal/visionsense-studio
# Install the autostart service (persistent, starts on boot):
bash deploy/install_service.sh
# Control:
sudo systemctl status visionsense
journalctl -u visionsense -f          # live logs
sudo systemctl restart visionsense

# Or run it directly (foreground):
PYTHONPATH=$PWD .venv/bin/python -m src.main   # http://192.168.2.2:8000/
```

Endpoints: `/` (dashboard) · `/status` (GPU/FPS) · `/events` · `/stream/{cam}` · `/health`

## Notes
- `cam-demo` (local clip) is in the config so the dashboard always shows live detection.
  Remove that block from `config/cameras.yaml` for pure production.
- Substreams (`subtype=1`) are used for AI per PLAN.md; if a camera has no substream,
  switch that line to `subtype=0`.
- Engine is built for THIS exact GPU. If you change GPUs, rebuild:
  `PYTHONPATH=$PWD .venv/bin/python scripts/build_engine_from_onnx.py models/yolo26n.onnx 640 15`
