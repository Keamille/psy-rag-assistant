# 一键启动全部容器。用法： .\scripts\up.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已生成 .env，请填写 APP_SECRET_KEY 与 JWT_SECRET 后重新运行。" -ForegroundColor Yellow
    exit 0
}

docker compose up -d --build
docker compose ps
Write-Host ""
Write-Host "访问 http://localhost:8080" -ForegroundColor Cyan
Write-Host "就绪探针： curl http://localhost:8080/api/v1/ready" -ForegroundColor DarkGray

