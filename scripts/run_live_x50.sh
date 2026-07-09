#!/bin/bash
# Live xlarge on 50 real NVR cameras, annotated tiled mosaic served as RTSP on :8555.
cd /home/humza/Personal/visionsense-studio
sudo docker rm -f dslive 2>/dev/null
sudo docker run --rm --gpus all --net=host --ulimit nofile=65536:65536 \
  --name dslive \
  -v "$PWD/models/deepstream:/models" \
  -v "$PWD/models/deepstream/app_configs:/cfg" \
  nvcr.io/nvidia/deepstream:9.0-triton-multiarch \
  deepstream-app -c /cfg/live_x50.txt
