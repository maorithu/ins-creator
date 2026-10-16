#!/usr/bin/env zsh
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/node/bin:$PATH"
export PYTHONPATH="$ROOT_DIR"

echo "============================================================"
echo "  Ins-Creator — AI Dance Instagram Reel & CapCut Studio"
echo "============================================================"

if [ ! -d "$ROOT_DIR/frontend/dist" ]; then
  echo "[1/2] Building React Studio Frontend..."
  (cd "$ROOT_DIR/frontend" && npm run build)
fi

echo "[2/2] Starting Ins-Creator Studio Server at http://127.0.0.1:8000 ..."
exec "$ROOT_DIR/backend/.venv/bin/uvicorn" backend.main:app --host 127.0.0.1 --port 8000
