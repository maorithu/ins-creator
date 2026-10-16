#!/usr/bin/env zsh
# One-command setup + launch. Safe to re-run: each step is skipped when already done.
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/node/bin:$PATH"
export PYTHONPATH="$ROOT_DIR"
VENV="$ROOT_DIR/backend/.venv"

echo "============================================================"
echo "  Ins-Creator — AI Dance Instagram Reel & CapCut Studio"
echo "============================================================"

command -v python3 >/dev/null || { echo "❌ python3 not found (need Python 3.9+)"; exit 1; }
command -v npm >/dev/null || { echo "❌ npm not found (need Node.js 18+ — https://nodejs.org)"; exit 1; }

if [ ! -x "$VENV/bin/uvicorn" ] || [ "$ROOT_DIR/backend/requirements.txt" -nt "$VENV/.installed" ]; then
  echo "[1/4] Setting up Python environment..."
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip -q
  "$VENV/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt" -q
  touch "$VENV/.installed"
fi

if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  echo "[2/4] Installing frontend packages..."
  (cd "$ROOT_DIR/frontend" && npm install --no-fund --no-audit)
fi

if [ ! -d "$ROOT_DIR/frontend/dist" ] || [ -n "$(find "$ROOT_DIR/frontend/src" -newer "$ROOT_DIR/frontend/dist/index.html" -print -quit 2>/dev/null)" ]; then
  echo "[3/4] Building React Studio frontend..."
  (cd "$ROOT_DIR/frontend" && npm run build)
fi

if [ ! -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  echo "ℹ️  Created .env from .env.example — add your GEMINI_API_KEY / GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET there."
fi

echo "[4/4] Starting Ins-Creator Studio at http://127.0.0.1:8000 ..."
exec "$VENV/bin/uvicorn" backend.main:app --host 127.0.0.1 --port 8000
