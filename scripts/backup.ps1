# 备份三件套（Windows 等价实现）。用法： .\scripts\backup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = ".\backups\$stamp"
New-Item -ItemType Directory -Path $out -Force | Out-Null

# SQLite 在 WAL 模式下直接拷贝文件可能损坏，必须用 .backup 做一致性快照
docker compose exec -T web sh -c "sqlite3 /data/app.db `".backup '/data/app.db.bak'`""
docker compose cp web:/data/app.db.bak "$out/app.db"

docker run --rm -v psy-rag-assistant_app_data:/src -v "${PWD}\$out:/dest" alpine `
    sh -c "cd /src && tar czf /dest/uploads.tar.gz uploads 2>/dev/null || true"

docker run --rm -v psy-rag-assistant_chroma_data:/src -v "${PWD}\$out:/dest" alpine `
    sh -c "cd /src && tar czf /dest/chroma_data.tar.gz ."

if (Test-Path ".env") { Copy-Item ".env" "$out/env.backup" }

Write-Host "备份完成 -> $out" -ForegroundColor Green

