#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Host =="
uname -a
echo
echo "== Docker =="
docker info --format 'CPUs={{.NCPU}} Memory={{.MemTotal}}' 2>/dev/null || true
docker compose -f "${ROOT_DIR}/docker-compose.mac.yml" ps 2>/dev/null || \
  docker compose -f "${ROOT_DIR}/docker-compose.yml" ps 2>/dev/null || true
echo
echo "== Native media =="
curl -fsS http://127.0.0.1:9010/v1/capabilities || true
echo
curl -fsS http://127.0.0.1:9010/v1/pipelines || true
echo
echo "== API =="
curl -fsS http://127.0.0.1:8000/health || true
echo
