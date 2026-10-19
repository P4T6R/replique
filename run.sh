#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -f frontend/dist/index.html ]]; then
  echo 'Compilez d’abord : cd frontend && npm ci && npm run build' >&2
  exit 1
fi
exec python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log
