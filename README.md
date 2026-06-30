# WaveMonitor

股票与衍生品价格监控服务：按配置的标的与数据源轮询行情，在触及支撑/阻力等规则时记录告警，并可通过 Telegram 推送。

## 功能概览

- **标的管理**：配置名称、支撑/阻力、阈值及多数据源映射（交易所、品种、是否启用）
- **仪表盘**：系统运行状态、最新价格、近期告警、数据源错误
- **Telegram**：配置 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID` 后可发送测试消息与告警

## 技术栈

| 层级 | 说明 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、SQLModel、SQLite |
| 前端 | React、TypeScript、Vite、Wouter |
| 部署 | Docker Compose（Nginx 反代前端并转发 `/api`） |

API 约定见 [`backend/API_CONTRACT.md`](backend/API_CONTRACT.md)。

## 快速开始（Docker）

```bash
cd /path/to/wavemonitor

# 可选：在项目根目录创建 .env
# TELEGRAM_BOT_TOKEN=...
# TELEGRAM_CHAT_ID=...

docker compose up --build -d
```

- **Web 界面**：<http://localhost:54002>
- **后端健康检查**（容器内或映射端口）：`GET /health`（Compose 默认仍将后端映射到宿主机 `8000`，前端经 Nginx 代理访问 API，日常使用只需打开 54002）

停止服务：

```bash
docker compose down
```

数据卷 `wavemonitor-sqlite` 持久化 SQLite 数据库。

## 本地开发

### 后端

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[test]"
uvicorn wavemonitor_backend.app:app --reload --app-dir backend/src
```

默认数据库路径由环境变量 `DATABASE_URL` 控制（未设置时使用项目内 SQLite）。

运行测试：

```bash
pytest
```

### 前端

```bash
cd frontend
npm install
npm run build
npm test
```

开发服务器（需自行配置 API 代理或指向后端地址）：

```bash
npx vite
```

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy 连接串，Compose 中为 `sqlite:////data/wavemonitor.sqlite3` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（可选） |
| `TELEGRAM_CHAT_ID` | 接收消息的 Chat ID（可选） |
| `RUN_LIVE_SMOKE` | 设为 `1` 时才执行 `backend/scripts/live_smoke.py` 中的实网探测 |

## 目录结构

```text
wavemonitor/
├── backend/          # FastAPI 应用与测试
├── frontend/         # React 单页应用
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## 许可证

按仓库所有者约定使用；贡献前请阅读 `AGENTS.md`（面向 AI 协作者的项目说明）。