# WaveMonitor

行情轮询与告警。共享 React + TypeScript + Vite 前端；两套后端实现同一 HTTP 契约。

| 运行时 | 栈 | 代码 |
| --- | --- | --- |
| 传统 | FastAPI + SQLModel + SQLite | `backend/` |
| Cloudflare | Workers + D1 + Cron（`*/2 * * * *`） | `worker/` |
| 前端 | React + Vite；Zod 在 API 边界 | `frontend/` |

权威：当前代码与 `backend/API_CONTRACT.md`。`.omo/plans/` 仅供追溯。

## 地图

- `backend/src/wavemonitor_backend/` · `backend/tests/`
- `worker/src/` · `worker/tests/` · `worker/migrations/`
- `frontend/src/` · `frontend/tests/` · `frontend/src/api/schemas.ts`
- `frontend/DESIGN.md`：UI 规范（无新 CSS 框架）
- `README.md`、`.env.example`：运行、部署、环境变量

Worker 独有：`POST /api/setup`、`GET/PUT /api/settings`。Worker 不支持 `BINANCE_HTTPS_PROXY`。

## 改动

- 行为变更或修缺陷：补回归测试。
- HTTP/契约变更：同步契约、**两套后端**、前端 Zod/client 与相关测试。只改一侧不算完成。
- 前端：入站 API 数据必须经 Zod 校验；保留无障碍语义。
- 端口或代理变更：同步 `docker-compose.yml`、`frontend/docker/nginx.conf`、`README.md`。
- 不暴露密钥；不提交 `.env`、构建产物、SQLite。
- 用户文档中文；代码注释与 API 契约英文。

## 验证

按改动范围：

```bash
pytest
ruff check backend/src backend/tests
(cd frontend && npm test && npm run build)
(cd worker && npm test && npm run check)
docker compose config   # 仅编排或代理
```

Python 业务逻辑必须 `pytest`；前端必须测试与构建；Worker 行为必须 `npm test`。
