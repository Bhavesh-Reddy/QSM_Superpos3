#!/usr/bin/env bash
# Start the QuMail KM simulator (ETSI 014) on http://127.0.0.1:8100
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ -x ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
else PY="python"; fi
echo "[QuMail] KM simulator -> http://127.0.0.1:8100"
exec "$PY" -m km_simulator.main
