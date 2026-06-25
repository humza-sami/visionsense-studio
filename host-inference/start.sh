#!/bin/bash
# VisionSense Host Inference Server — starts YOLO on Mac Metal (MPS)
set -e
cd "$(dirname "$0")"

PYTHON=/opt/homebrew/bin/python3.13
VENV=".venv"

# Create venv if needed
if [ ! -d "$VENV" ]; then
    echo "Creating Python venv..."
    "$PYTHON" -m venv "$VENV"
fi

source "$VENV/bin/activate"

# Install/upgrade deps
echo "Checking dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "Starting host inference server on http://0.0.0.0:9020"
echo "Docker backend will route AI calls to http://host.docker.internal:9020"
echo ""
python server.py
