# Production image for the Ubuntu / NVIDIA box. Build & run with the NVIDIA
# Container Toolkit (`--gpus all`). Base on a CUDA+cuDNN runtime that matches the
# host driver; TensorRT is pip-installed to match.
#
#   docker build -f docker/Dockerfile -t visionsense .
#   docker run --gpus all -p 8000:8000 visionsense
#
# NOTE: the pip opencv wheel has NO GStreamer support. This image therefore uses
# the OpenCV/FFmpeg capture path by default. For NVDEC GStreamer decode, either
# install gstreamer plugins + build OpenCV with GStreamer, or switch capture to
# PyNvVideoCodec (see README §Prod decode).

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev \
    libgl1 libglib2.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install --no-cache-dir pynvml tensorrt onnx onnxruntime-gpu

COPY . .

# Build the engine on first run if missing, then start (engines are GPU-specific).
EXPOSE 8000
CMD ["python3", "-m", "src.main"]
