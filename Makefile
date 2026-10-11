# 心理咨询 AI 助手 —— 常用命令封装
# Windows 用户请优先使用 scripts/*.ps1；此 Makefile 主要面向 macOS / WSL

.PHONY: help init dev dev-backend dev-frontend up down logs ps build backup test lint clean

help:
	@echo "可用目标："
	@echo "  make init          复制 .env.example 为 .env（已存在则跳过）"
	@echo "  make up            启动全部容器"
	@echo "  make down          停止并移除容器"
	@echo "  make build         重建镜像"
	@echo "  make logs          跟踪 web 日志"
	@echo "  make ps            查看容器状态"
	@echo "  make dev-backend   宿主机跑 Flask 开发服务器"
	@echo "  make dev-frontend  宿主机跑 Vite 开发服务器"
	@echo "  make test          跑后端测试"
	@echo "  make backup        备份三件套"
	@echo "  make clean         清理缓存与构建产物"

init:
	@test -f .env || cp .env.example .env
	@echo ".env 就绪"

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f web

ps:
	docker compose ps

dev-backend:
	cd backend && ../.venv/bin/python run.py

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && ../.venv/bin/python -m pytest

backup:
	./scripts/backup.sh

clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	rm -rf backend/.pytest_cache frontend/dist

