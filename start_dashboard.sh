#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Missing .venv in $ROOT_DIR. Please create it first."
  exit 1
fi

if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  echo "Missing frontend node_modules. Run npm install inside frontend first."
  exit 1
fi

API_PID=""
WEB_PID=""

cleanup() {
  [[ -z "$API_PID" ]] || kill "$API_PID" 2>/dev/null || true
  [[ -z "$WEB_PID" ]] || kill "$WEB_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR"
"$ROOT_DIR/.venv/bin/python" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

echo "Waiting for API gateway to become ready..."
for _ in {1..50}; do
  if curl --silent --fail http://127.0.0.1:8000/api/health >/dev/null; then
    break
  fi
  sleep 0.2
done

if ! curl --silent --fail http://127.0.0.1:8000/api/health >/dev/null; then
  echo "The API did not become ready on port 8000."
  exit 1
fi

cd "$ROOT_DIR/frontend"
npm run dev -- --host 127.0.0.1 &
WEB_PID=$!

echo "=========================================================="
echo " Digital-City-Expand Web Operations Dashboard is running! "
echo " Dashboard UI: http://127.0.0.1:5173"
echo " API Docs:     http://127.0.0.1:8000/docs"
echo " Press Ctrl+C to stop all services."
echo "=========================================================="

wait
