#!/usr/bin/env bash
# Start the QuMail backend API on http://127.0.0.1:8000
# Requires a .env file (copy .env.example -> .env and set KEYSTORE_MASTER_PASSWORD).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ ! -f ".env" ]; then
  echo "[QuMail] ERROR: .env not found. Copy .env.example to .env and set KEYSTORE_MASTER_PASSWORD." >&2
  exit 1
fi
if [ -x ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
else PY="python"; fi
echo "[QuMail] backend API -> http://127.0.0.1:8000"
exec "$PY" -m backend.main
