#!/usr/bin/env bash
# 备份三件套：SQLite 一致性快照 + 上传原件 + Chroma 向量卷
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="./backups/$STAMP"
mkdir -p "$OUT"

# SQLite 在 WAL 模式下直接拷贝文件可能损坏，必须用 .backup 做一致性快照
docker compose exec -T web sh -c "sqlite3 /data/app.db \".backup '/data/app.db.bak'\""
docker compose cp web:/data/app.db.bak "$OUT/app.db"

docker run --rm -v psy-rag-assistant_app_data:/src -v "$PWD/$OUT:/dest" alpine \
  sh -c "cd /src && tar czf /dest/uploads.tar.gz uploads 2>/dev/null || true"

docker run --rm -v psy-rag-assistant_chroma_data:/src -v "$PWD/$OUT:/dest" alpine \
  sh -c "cd /src && tar czf /dest/chroma_data.tar.gz ."

[[ -f .env ]] && cp .env "$OUT/env.backup"

echo "备份完成 -> $OUT"

