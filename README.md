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

---

## 环境要求

### 使用 Docker 部署（推荐）

| 依赖 | 版本建议 |
| --- | --- |
| Docker | 24+ |
| Docker Compose | v2（`docker compose` 子命令） |
| 磁盘 | 约 500MB 镜像与构建缓存；数据库在命名卷中增长 |
| 网络 | 容器需访问外网以拉取 Binance / Hyperliquid / Yahoo Finance 等行情 |

### 本地开发

| 依赖 | 版本建议 |
| --- | --- |
| Python | 3.11+ |
| Node.js | 20+（与 `frontend/Dockerfile` 中 Node 24 构建环境兼容即可） |
| npm | 随 Node 安装 |

---

## 安装与部署（Docker Compose）

以下步骤假设已将仓库克隆到本机，并在**项目根目录**（含 `docker-compose.yml` 的目录）执行命令。

### 1. 获取代码

```bash
git clone <你的仓库地址> wavemonitor
cd wavemonitor
```

若你已有源码目录，直接进入该目录即可。

### 2. 配置环境变量

在项目根目录复制示例文件并编辑：

```bash
cp .env.example .env
```

**完整配置示例**（按需修改；勿将含真实 Token 的 `.env` 提交到 Git）：

```bash
# ---------- Telegram（可选；不填则仅 Web 告警，不推送）----------
# 在 @BotFather 创建 Bot 后获得的 Token
TELEGRAM_BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# 接收告警的 Chat ID（可为个人、群组或频道；频道常用 -100 开头）
TELEGRAM_CHAT_ID=-1001234567890

# ---------- 本地开发常用（Docker Compose 默认不读取下列变量，见下文说明）----------
# 后端监听（本地 uvicorn 时使用）
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
# 前端开发服务器端口
FRONTEND_PORT=5173
# 本地 SQLite（相对路径，文件落在项目根目录）
DATABASE_URL=sqlite:///./wavemonitor.sqlite3
# 本地前端请求后端的根地址；生产 Docker 前端走同源 /api，无需设置
VITE_API_BASE_URL=http://localhost:8000

# ---------- 可选：实网冒烟脚本（默认不跑）----------
# RUN_LIVE_SMOKE=1
```

**Docker Compose 实际注入后端的变量**（定义在 `docker-compose.yml`）：

| 变量 | Compose 中的值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:////data/wavemonitor.sqlite3` | 固定写在 compose 中，覆盖 `.env` 里同名项对**容器**无效 |
| `TELEGRAM_BOT_TOKEN` | 从宿主机 `.env` 或环境传入 | 空则 Telegram 未就绪 |
| `TELEGRAM_CHAT_ID` | 从宿主机 `.env` 或环境传入 | 须与 Token 同时配置 |

Compose **不会**自动把 `WAVEMONITOR_POLL_INTERVAL_SECONDS`、`WAVEMONITOR_MONITORING_DISABLED` 传入容器。若要在 Docker 中调整轮询间隔或关闭调度，在 `docker-compose.yml` 的 `backend.environment` 中增加，例如：

```yaml
    environment:
      DATABASE_URL: sqlite:////data/wavemonitor.sqlite3
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}
      TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID:-}
      WAVEMONITOR_POLL_INTERVAL_SECONDS: "60"
      # WAVEMONITOR_MONITORING_DISABLED: "1"   # 设为 1/true/yes 可关闭后台轮询
```

### 3. 构建并启动

```bash
docker compose up --build -d
```

首次会构建 `backend`、`frontend` 镜像。`frontend` 会等待 `backend` 健康检查通过后再启动。

### 4. 访问与验证

| 入口 | 地址 | 说明 |
| --- | --- | --- |
| **Web 管理界面** | <http://localhost:54002> | 日常使用入口；`/api` 由 Nginx 转发到后端 |
| 后端 API（直连） | <http://localhost:8000> | 调试、脚本调用 |
| 健康检查 | <http://localhost:54002/health> 或 <http://localhost:8000/health> | 应返回 JSON，含 `status`、`telegram_ready` |

命令行快速检查：

```bash
curl -s http://localhost:54002/health | python3 -m json.tool
curl -s http://localhost:8000/api/runtime | python3 -m json.tool
```

在 Web 界面中：

1. 打开 **Instruments**，新建标的并配置支撑/阻力、阈值及数据源（YFinance / Binance / Hyperliquid 等）。
2. 在 **Dashboard** 查看 `scheduler_ready`、`polled_sources`、最新价格与告警。
3. 若已配置 Telegram，使用界面中的 Telegram 测试（或 `POST /api/telegram/test`）确认推送。

### 5. 日常运维

```bash
# 查看日志
docker compose logs -f
docker compose logs -f backend
docker compose logs -f frontend

# 停止服务（保留数据卷）
docker compose down

# 停止并删除数据库卷（清空 SQLite，慎用）
docker compose down -v

# 重新构建并滚动更新
docker compose up --build -d
```

**数据持久化**：SQLite 保存在 Docker 命名卷 `wavemonitor-sqlite`，挂载到后端容器 `/data/wavemonitor.sqlite3`。删除卷会丢失全部标的与历史观测数据。

**端口说明**：

- `54002:8080` — 前端 Nginx（对外 Web）
- `8000:8000` — 后端 FastAPI（可选直连；前端容器通过服务名 `backend:8000` 访问 API）

修改对外端口时，请同步改 `docker-compose.yml` 与本 README。

---

## Telegram 配置说明

1. 在 Telegram 中联系 [@BotFather](https://t.me/BotFather)，执行 `/newbot`，按提示创建 Bot，保存 **Bot Token**（形如 `数字:字母数字`）。
2. 获取 **Chat ID**：
   - **个人**：先给 Bot 发一条消息，再访问 `https://api.telegram.org/bot<TOKEN>/getUpdates`，在 JSON 中查看 `message.chat.id`。
   - **群组**：将 Bot 拉入群并发言一次，同样在 `getUpdates` 中查看群的 `id`（常为负数）。
   - **频道**：将 Bot 设为管理员，频道 ID 多为 `-100` 开头。
3. 将 Token 与 Chat ID 写入项目根目录 `.env` 的 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`。
4. 重启后端使环境变量生效：

   ```bash
   docker compose up -d --force-recreate backend
   ```

5. 确认 `GET /health` 或 Dashboard 中 `telegram_ready` 为 `true`，再发送测试消息。

密钥仅由**后端**进程读取；前端与 Nginx 不接收 Telegram 环境变量。日志与 API 会对敏感信息脱敏。

---

## 环境变量参考

| 变量 | 默认值 / 行为 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 本地：`sqlite:///./wavemonitor.sqlite3` | SQLAlchemy 连接串；Docker 后端使用卷内绝对路径 |
| `TELEGRAM_BOT_TOKEN` | 无 | Telegram Bot Token（可选） |
| `TELEGRAM_CHAT_ID` | 无 | 告警接收方 Chat ID（可选） |
| `WAVEMONITOR_POLL_INTERVAL_SECONDS` | `60` | 行情轮询周期（秒），须 > 0 |
| `WAVEMONITOR_MONITORING_DISABLED` | 未设置 | 设为 `1` / `true` / `yes` 时关闭后台调度（仅 API，不轮询） |
| `RUN_LIVE_SMOKE` | 未设置 | 设为 `1` 时执行 `backend/scripts/live_smoke.py` 实网探测 |
| `VITE_API_BASE_URL` | 空字符串 | **仅本地前端构建/开发**：API 根地址；Docker 生产构建留空，使用同源 `/api` |
| `BACKEND_HOST` / `BACKEND_PORT` | 文档示例用 | 本地启动说明用；镜像内后端固定 `0.0.0.0:8000` |
| `FRONTEND_PORT` | `5173` | 文档示例用；`npx vite` 默认端口 |

---

## 本地开发

适合改代码、跑测试，**不依赖 Docker**。

### 后端

在**项目根目录**：

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[test]"

# 可选：加载 .env（若未 export，可手动 export 或使用 direnv）
export DATABASE_URL=sqlite:///./wavemonitor.sqlite3
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...

uvicorn wavemonitor_backend.app:app --reload --app-dir backend/src --host 0.0.0.0 --port 8000
```

运行测试：

```bash
pytest
```

### 前端

```bash
cd frontend
npm ci
npm test
npm run build
```

开发服务器（需能访问后端 API）：

```bash
# 方式 A：通过环境变量指向后端（与 .env.example 一致）
export VITE_API_BASE_URL=http://localhost:8000
npx vite --host 0.0.0.0 --port 5173

# 方式 B：不设置 VITE_API_BASE_URL 时，请求为相对路径 /api/...
# 需在 vite.config.ts 中自行添加 server.proxy，将 /api 与 /health 代理到 http://localhost:8000
```

本地联调时，先启动后端（8000），再启动前端（5173），浏览器打开 Vite 提示的地址。

### 与 Docker 的差异

| 项目 | 本地开发 | Docker |
| --- | --- | --- |
| 数据库文件 | 项目根目录 `wavemonitor.sqlite3` | 卷 `wavemonitor-sqlite` |
| 前端访问 API | `VITE_API_BASE_URL` 或 Vite proxy | Nginx 同源 `/api` |
| 对外端口 | 5173 + 8000 | **54002**（Web）+ 8000（API） |

---

## 目录结构

```text
wavemonitor/
├── backend/                 # FastAPI 应用、Dockerfile、测试
│   ├── src/wavemonitor_backend/
│   ├── tests/
│   └── API_CONTRACT.md
├── frontend/                # React SPA、Nginx 配置、Dockerfile
├── docker-compose.yml
├── .env.example             # 环境变量模板（复制为 .env）
├── pyproject.toml
├── AGENTS.md                # AI 协作者说明
└── README.md
```

---

## 常见问题

**Q：界面打不开或 API 404**  
检查 `docker compose ps` 是否两个服务均为 `running`，`backend` 为 `healthy`。查看 `docker compose logs frontend` 中 Nginx 是否正常。

**Q：`telegram_ready` 一直为 false**  
确认 `.env` 中两项均已填写且无多余引号/空格，并执行 `docker compose up -d --force-recreate backend`。

**Q：有标的但 Dashboard 无价格**  
确认标的已启用、数据源映射已启用且 symbol 正确；查看 Dashboard 数据源错误区与 `GET /api/source-errors`。容器需能访问外网。

**Q：如何备份数据**  
从卷中拷贝 SQLite 文件，例如：

```bash
docker compose exec backend cat /data/wavemonitor.sqlite3 > wavemonitor-backup.sqlite3
```

---

## 许可证

按仓库所有者约定使用；贡献前请阅读 `AGENTS.md`（面向 AI 协作者的项目说明）。