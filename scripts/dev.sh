#!/usr/bin/env bash
# 本地开发：后端 Flask（热重载）。前端请另开终端执行 cd frontend && npm run dev
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "未找到 .venv。请先执行： python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt" >&2
  exit 1
fi

cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" run.py

