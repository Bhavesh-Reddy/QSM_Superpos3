#!/usr/bin/env bash
# Start the QuMail frontend (Vite dev server; use electron:dev for the desktop shell).
set -euo pipefail
cd "$(dirname "$0")/../frontend"
if [ ! -d "node_modules" ]; then
  echo "[QuMail] Installing frontend dependencies..."
  npm install
fi
echo "[QuMail] frontend dev server -> http://127.0.0.1:5173"
exec npm run dev
