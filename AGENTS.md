# WaveMonitor 工作指南

WaveMonitor 是行情轮询与告警服务：FastAPI + SQLModel + SQLite 后端，React + TypeScript + Vite 前端。

## 代码与契约

- `backend/src/wavemonitor_backend/`、`backend/tests/`：后端实现与 pytest 测试
- `frontend/src/`、`frontend/tests/`：前端实现与 Vitest 测试
- `backend/API_CONTRACT.md`：HTTP API 契约
- `frontend/src/api/schemas.ts`：前端 API 数据的 Zod 边界
- `frontend/DESIGN.md`：UI 规范
- `README.md`、`.env.example`：运行、部署与环境变量说明

以当前代码和契约为准；`.omo/plans/` 仅供追溯，不作为实现依据。

## 修改规则

- 后端行为变更或缺陷修复应补回归测试；API 变更同时更新契约、前端 schema/client 及相关测试。
- 前端接收的 API 数据必须经 Zod 校验；保留无障碍语义，遵循 `frontend/DESIGN.md`，不新增 CSS 框架。
- 部署端口或代理变更时，同步 `docker-compose.yml`、`frontend/docker/nginx.conf` 与 `README.md`。
- 不在代码、日志、API 响应或提交内容中暴露密钥；不提交本地环境、构建产物或 SQLite 数据。
- 面向用户的文档使用中文；代码注释和 API 契约使用英文。

## 验证

按改动范围运行：

```bash
pytest
ruff check backend/src backend/tests
(cd frontend && npm test && npm run build)
docker compose config  # 仅编排或代理配置变更
```

后端业务逻辑必须运行 `pytest`；前端改动必须运行测试与构建。
