# 本地开发：后端 Flask（热重载）。前端请另开终端执行 cd frontend; npm run dev
# 用法： .\scripts\dev.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
    Write-Host "未找到 .venv。请先执行： python -m venv .venv；再装 backend\requirements-dev.txt" -ForegroundColor Yellow
    exit 1
}

Write-Host "启动后端 http://127.0.0.1:5000 ..." -ForegroundColor Cyan
$backend = Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
    -ArgumentList "run.py" `
    -WorkingDirectory "$root\backend" `
    -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput "$root\srv.out.log" `
    -RedirectStandardError "$root\srv.err.log"

Write-Host "pid=$($backend.Id)  日志： srv.out.log / srv.err.log" -ForegroundColor Cyan
Write-Host "停止后端： Stop-Process -Id $($backend.Id)" -ForegroundColor DarkGray

