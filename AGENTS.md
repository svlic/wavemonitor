# WaveMonitor

行情轮询与告警。React + TypeScript + Vite 前端；FastAPI + SQLModel + SQLite 后端。

| 运行时 | 栈 | 代码 |
| --- | --- | --- |
| 后端 | FastAPI + SQLModel + SQLite | `backend/` |
| 前端 | React + Vite；Zod 在 API 边界 | `frontend/` |

权威：当前代码与 `backend/API_CONTRACT.md`。`.omo/plans/` 仅供追溯。

## 地图

- `backend/src/wavemonitor_backend/` · `backend/tests/`
- `frontend/src/` · `frontend/tests/` · `frontend/src/api/schemas.ts`
- `frontend/DESIGN.md`：UI 规范（无新 CSS 框架）
- `README.md`、`.env.example`：运行、部署、环境变量

## 改动

- 行为变更或修缺陷：补回归测试。
- HTTP/契约变更：同步契约、后端、前端 Zod/client 与相关测试。
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
docker compose config   # 仅编排或代理
```

Python 业务逻辑必须 `pytest`；前端必须测试与构建。
