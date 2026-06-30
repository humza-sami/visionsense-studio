"""Build a TensorRT FP16 engine directly from the exported ONNX, using the
TensorRT Python API — no `nvidia-modelopt` needed (recent Ultralytics pulls a ~4GB
modelopt[onnx] tree just to call TRT; this sidesteps that entirely).

Embeds Ultralytics-compatible metadata so `YOLO("....engine")` loads it unchanged.

  python scripts/build_engine_from_onnx.py [models/yolo26n.onnx] [imgsz] [max_batch]
"""
from __future__ import annotations

import json
import sys
import time

import tensorrt as trt


def main() -> int:
    onnx_path = sys.argv[1] if len(sys.argv) > 1 else "models/yolo26n.onnx"
    imgsz = int(sys.argv[2]) if len(sys.argv) > 2 else 640
    max_b = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    opt_b = max(1, min(8, max_b))
    engine_path = onnx_path.replace(".onnx", ".engine")

    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)

    # TRT 10+: networks are explicit-batch by default; the flag is gone.
    try:
        flag = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
        network = builder.create_network(flag)
    except AttributeError:
        network = builder.create_network(0)

    parser = trt.OnnxParser(network, logger)
    with open(onnx_path, "rb") as f:
        if not parser.parse(f.read()):
            for i in range(parser.num_errors):
                print("ONNX parse error:", parser.get_error(i))
            return 1

    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 4 << 30)  # 4 GB cap
    # Precision flags vary by TRT version (newer builds drop the global FP16 flag in
    # favour of strongly-typed networks). Enable whatever this binding exposes; TF32
    # tensor-core acceleration on Ampere is the default-on fast path either way.
    flags = []
    for flag_name in ("FP16", "TF32"):
        flag = getattr(trt.BuilderFlag, flag_name, None)
        if flag is not None:
            config.set_flag(flag)
            flags.append(flag_name)
    print("precision flags:", flags or ["FP32"])

    inp = network.get_input(0)
    profile = builder.create_optimization_profile()
    profile.set_shape(inp.name,
                      (1, 3, imgsz, imgsz),
                      (opt_b, 3, imgsz, imgsz),
                      (max_b, 3, imgsz, imgsz))
    config.add_optimization_profile(profile)
    print(f"input '{inp.name}' dynamic batch 1/{opt_b}/{max_b} @ {imgsz}px — building…")

    t0 = time.monotonic()
    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        print("Engine build FAILED")
        return 1
    print(f"built in {time.monotonic() - t0:.1f}s")

    # Ultralytics metadata header: 4-byte little-endian length + JSON, then engine.
    from ultralytics import YOLO
    names = YOLO("models/yolo26n.pt").names
    meta = {
        "description": "Ultralytics YOLO26n",
        "author": "Ultralytics",
        "version": "8.4.83",
        "stride": 32,
        "task": "detect",
        "batch": max_b,
        "imgsz": [imgsz, imgsz],
        "names": names,
    }
    meta_b = json.dumps(meta).encode()
    with open(engine_path, "wb") as f:
        f.write(len(meta_b).to_bytes(4, byteorder="little"))
        f.write(meta_b)
        f.write(serialized)
    import os
    print(f"wrote {engine_path}  ({os.path.getsize(engine_path)/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
