# 心理咨询 AI 助手

基于 RAG 的心理咨询辅助系统，Flask 前后端分离。完整设计与接口契约见
[`docs/心理咨询AI助手_开发文档.md`](docs/心理咨询AI助手_开发文档.md)。

> 本系统不是医疗器械，不提供诊断、治疗、处方或急救服务，不能替代精神科医生
> 与临床心理师的面对面评估。识别到自伤风险时会中断 AI 应答并引导至求助渠道。

---

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
cp .env.example .env        # Windows: Copy-Item .env.example .env
```

编辑 `.env`，至少填两项随机密钥，以及大模型的接入信息：

```dotenv
APP_SECRET_KEY=<64 位随机串>
JWT_SECRET=<另一串 64 位随机串>
LLM_API_KEY=<你的模型服务密钥>
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

```bash
docker compose up -d --build
docker compose ps          # 五个服务都应为 healthy / Up
curl http://localhost:8080/api/v1/ready
```

首次构建要下载 PyTorch 等约 2–3 GB 依赖（镜像约 3–4 GB），请预留 15 GB 磁盘。
只想快速看界面时可以在命令前加 `BACKEND_REQ_FILE=requirements-base.txt`，
但那样容器内没有向量化能力，检索会静默退化为纯 BM25。

打开 <http://localhost:8080>，注册账号即可开始使用。

### 方式二：本地开发（改代码时用）

后端：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt   # Windows
# .venv/bin/pip install -r backend/requirements-dev.txt                   # macOS

cd backend
..\.venv\Scripts\python.exe run.py     # 默认 127.0.0.1:5000，用 PORT 环境变量改
```

前端：

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173，已配好 /api 代理到 127.0.0.1:5000
```

RAG 需要两个外部依赖，本地开发时得自己起：**Chroma**（向量库）与 **Redis**（任务队列、限流）。

```bash
docker run -d --name psy-chroma -p 8001:8000 chromadb/chroma:0.5.23
docker run -d --name psy-redis  -p 6379:6379 redis:7-alpine
```

并让 `.env` 里的 `CHROMA_HOST=localhost`、`CHROMA_PORT=8001` 对应上。

### 首次启动要做的事

**1. 下载模型权重**（约 4.6GB，只需一次）

```bash
python backend/scripts/download_models.py --target ./models/hf-cache
```

不要设 `HF_ENDPOINT` 为镜像站——镜像的 `resolve` 端点缺少 huggingface_hub
所需的元数据响应头，会直接失败；且它通常不支持多线程大文件下载。

**2. 内置语料入库**

容器启动时会自动执行（`seed-knowledge`），本地开发时手动跑一次：

```bash
cd backend && ..\.venv\Scripts\python.exe -m app.cli seed-knowledge
```

**3. 创建管理员**（容器内自动执行，本地手动）

```bash
cd backend && ..\.venv\Scripts\python.exe -m app.cli init-admin
```

默认账号 `admin` / `ChangeMe12345`，首次登录后请立即修改。

### 在 PyCharm 中打开

仓库带 `.idea` 配置，打开后若提示找不到解释器，在
**Settings → Project → Python Interpreter** 选 `.venv\Scripts\python.exe` 即可。
预置三条运行配置：`Flask: run.py`、`pytest: backend`、`RQ worker: ingest`。

---

## 常用命令

| 目的 | 命令 |
|---|---|
| 起 / 停容器 | `docker compose up -d --build` / `docker compose down` |
| 改完代码重建镜像 | `docker compose up -d --build`（**不带 `--build` 会复用旧镜像**） |
| 看日志 | `docker compose logs -f web` |
| 跑测试 | `cd backend && ..\.venv\Scripts\python.exe -m pytest` |
| 前端构建 | `cd frontend && npm run build` |
| 备份 / 恢复 | `./scripts/backup.sh` / `./scripts/restore.sh <备份目录>` |

---

## 关键设计

### 1. 风险判定前置，且用规则与模型双通道

自伤/自杀风险的判定**必须发生在生成之前**——一旦高危用户先看到一段温和的
AI 安慰，伤害就已经造成，事后再打断也补不回来。命中高危时中断本轮应答、
锁定会话、写入危机事件，且**不产生任何流式片段**（否则前端会显示成
"回答到一半没了"）。

判定用两层串联：规则层扫词典负责不漏（显式表达、隐晦措辞、否定语境过滤），
模型层负责摘掉规则层的误报（引用、转述、玩笑）并补上词典覆盖不到的隐晦表达。
成本是不对称的——漏报的代价远大于误报，所以模型确认超时或失败时按规则层
结果保守处置；但所有触发都会落库，供人工复核。

### 2. 混合检索 + 重排，全都不过阈值就拒答

单一向量检索会漏掉专有名词与用户复述原文这两类查询，单一关键词检索又对
同义改写无能为力，所以两路各召回 20 条，用 RRF 融合（只用排名、不用分数，
免疫量纲差异），再用 Cross-Encoder 重排取前 5。

架构上是**召回求全、重排求准**：双塔检索时 query 与文档各自独立编码、
互不知情，精度有结构性上限；Cross-Encoder 让它们拼接后直接交互，更准但
每对都要跑一次完整前向，所以只能对少量候选做。

如果所有候选的重排分数都低于阈值，**返回空列表让系统走拒答分支**——
宁可说"我的知识库里没有相关资料"，也不要拿一段不相关的内容硬凑回答。

### 3. 流式输出与两级记忆

回答用 SSE 逐块推送 `meta → risk? → delta* → sources → done`，
回答里的 `[n]` 角标对应可展开的原文来源卡片。

记忆分两级：最近 6 轮以**原文**进上下文（心理支持依赖细节，压缩会丢信息），
更早的内容滚动压缩成结构化摘要长期保存。两级都要——只有摘要会丢细节，
只有原文会超上下文窗口。

---

## 目录结构

```text
psy-rag-assistant/
├── docker-compose.yml          # frontend / web / worker / redis / chroma
├── .env.example                # 环境变量全量模板
├── docs/心理咨询AI助手_开发文档.md
├── backend/
│   ├── app/
│   │   ├── api/v1/             # 路由层：只做解析、调用、组装响应
│   │   ├── services/           # 业务编排：对话、记忆、风险、文档
│   │   ├── rag/                # 解析、切分、向量化、检索、重排、Prompt
│   │   ├── models/             # 9 张表的 ORM 定义
│   │   ├── core/               # 响应包装、错误码、鉴权、限流、日志
│   │   └── data/               # 内置语料、风险词典、求助资源、免责声明
│   ├── migrations/             # Alembic 迁移
│   └── tests/                  # 单元 / 集成 / 安全用例
├── frontend/src/               # Vue 3 + Vite + TypeScript
└── scripts/                    # 开发、启停、备份恢复（ps1 + sh）
```

---

## 部署注意事项

| 项 | 说明 |
|---|---|
| 项目路径 | 构建镜像前建议移到**无空格、无中文**的路径（如 `D:\psy-rag-assistant`） |
| 首次构建 | 下载 PyTorch 等依赖约 2–3 GB；磁盘建议预留 15 GB |
| SSE 缓冲 | Nginx 必须保留 `proxy_buffering off;`，漏掉会让流式回答变成"转圈很久后整段蹦出来" |
| 模型权重 | 容器不挂载宿主机的模型目录时会重新下载 4.6GB；用 `./models/hf-cache:/models/hf-cache` 挂载可复用 |
| 内存 | 两个模型常驻约 4.6GB。Docker Desktop 默认内存上限可能不够，建议调到 ≥ 8GB |
| Redis 可选性 | Redis 不可用时鉴权、限流、任务队列会降级；注销会明确返回 503 而不是假装成功 |

---

## 许可与合规

- 仓库内不含任何真实密钥。`.env` 与模型权重均已在 `.gitignore` 中排除；
  对外部署前请重新生成 `APP_SECRET_KEY` 与 `JWT_SECRET`。
- 代码仅供内测使用。对外提供服务涉及互联网信息服务备案与相应资质要求。
- 内置心理学语料为**工程占位内容**，正式上线前需由具备心理学背景的人员重写与审校。
- 用户上传文档的版权责任由运营方承担。
- 危机场景的判定**一定会存在漏报**，任何自动化系统都无法承诺零漏报；
  必须配套人工跟进流程（见开发文档 §10.8）。

