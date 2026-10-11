# 从备份恢复（Windows 等价实现）。用法： .\scripts\restore.ps1 .\backups\20261004-120000
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$backup = $args[0]
if (-not $backup) { Write-Host "用法: .\scripts\restore.ps1 <备份目录>" -ForegroundColor Yellow; exit 1 }
if (-not (Test-Path $backup)) { Write-Host "备份目录不存在：$backup" -ForegroundColor Red; exit 1 }

$answer = Read-Host "将停止容器并覆盖当前数据，确认继续？输入 yes"
if ($answer -ne "yes") { Write-Host "已取消"; exit 0 }

Write-Host "停止容器 ..." -ForegroundColor Cyan
docker compose down

Write-Host "恢复 SQLite 与上传原件 ..." -ForegroundColor Cyan
docker run --rm -v psy-rag-assistant_app_data:/dest alpine sh -c "rm -rf /dest/* && mkdir -p /dest"
docker run --rm -v psy-rag-assistant_app_data:/dest -v "${PWD}\$backup:/src" alpine `
    sh -c "cp /src/app.db /dest/app.db && tar xzf /src/uploads.tar.gz -C /dest"

Write-Host "恢复 Chroma 向量 ..." -ForegroundColor Cyan
docker run --rm -v psy-rag-assistant_chroma_data:/dest alpine sh -c "rm -rf /dest/* && mkdir -p /dest"
docker run --rm -v psy-rag-assistant_chroma_data:/dest -v "${PWD}\$backup:/src" alpine `
    sh -c "tar xzf /src/chroma_data.tar.gz -C /dest"

Write-Host "启动容器 ..." -ForegroundColor Cyan
docker compose up -d

Write-Host "恢复完成。请检查 /api/v1/ready 与文档列表。" -ForegroundColor Green

