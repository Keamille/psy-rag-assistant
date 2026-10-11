#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已生成 .env，请填写 APP_SECRET_KEY 与 JWT_SECRET 后重新运行。" >&2
  exit 0
fi

docker compose up -d --build
docker compose ps
echo
echo "访问 http://localhost:8080"
echo "就绪探针： curl http://localhost:8080/api/v1/ready"

