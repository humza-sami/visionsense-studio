#!/bin/bash
# Multi-path 720p loopback relay: mediamtx + 12 publishers (live0..live11).
# Stays in foreground (waits) so the background-task parent keeps children alive.
cd /home/humza/Personal/visionsense-studio
fuser -k 8554/tcp 2>/dev/null; pkill -f stream_loop 2>/dev/null; sleep 2
~/mediamtx/mediamtx deploy/mediamtx_multi.yml > /tmp/mtx_multi.log 2>&1 &
MTX=$!
sleep 3
PUBS=()
for p in $(seq 0 11); do
  ffmpeg -re -stream_loop -1 -i test_assets/nvr_720p.mp4 -an -c:v copy \
    -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/live$p > /dev/null 2>&1 &
  PUBS+=($!)
done
sleep 5
echo "RELAY_UP mediamtx=$MTX publishers=${#PUBS[@]}"
wait $MTX
