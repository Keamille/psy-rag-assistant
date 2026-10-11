#!/usr/bin/env bash
# 从备份恢复。用法： ./scripts/restore.sh backups/20261004-120000
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKUP="${1:?用法: ./scripts/restore.sh <备份目录>}"
[[ -d "$BACKUP" ]] || { echo "备份目录不存在：$BACKUP" >&2; exit 1; }

read -r -p "将停止容器并覆盖当前数据，确认继续？(yes/N) " answer
[[ "$answer" == "yes" ]] || { echo "已取消"; exit 0; }

echo "停止容器 ..."
docker compose down

echo "恢复 SQLite 与上传原件 ..."
docker run --rm -v psy-rag-assistant_app_data:/dest alpine sh -c "rm -rf /dest/* && mkdir -p /dest"
docker run --rm -v psy-rag-assistant_app_data:/dest -v "$PWD/$BACKUP:/src" alpine \
  sh -c "cp /src/app.db /dest/app.db && tar xzf /src/uploads.tar.gz -C /dest"

echo "恢复 Chroma 向量 ..."
docker run --rm -v psy-rag-assistant_chroma_data:/dest alpine sh -c "rm -rf /dest/* && mkdir -p /dest"
docker run --rm -v psy-rag-assistant_chroma_data:/dest -v "$PWD/$BACKUP:/src" alpine \
  sh -c "tar xzf /src/chroma_data.tar.gz -C /dest"

echo "启动容器 ..."
docker compose up -d

echo "恢复完成。请检查 /api/v1/ready 与文档列表。"

