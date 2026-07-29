# WaveMonitor Agent Guide

## 项目

WaveMonitor 轮询多数据源行情，评估支撑/阻力规则，持久化价格与告警，并可发送 Telegram 通知。后端为 FastAPI + SQLModel，前端为 React + TypeScript。

## 代码与权威文档

- `backend/src/wavemonitor_backend/`：API、调度、行情适配、规则与通知
- `backend/tests/`：后端 pytest 测试
- `frontend/src/`、`frontend/tests/`：React 应用与 Vitest 测试
- `backend/API_CONTRACT.md`：HTTP API 权威契约
- `frontend/DESIGN.md`：UI 设计规范
- `README.md`、`.env.example`：部署、运行与环境变量说明

以当前代码和 API 契约为准；`.omo/plans/` 仅是历史记录。

## 验证命令

```bash
# 仓库根目录
pytest
ruff check backend/src backend/tests

# 前端
cd frontend && npm test && npm run build

# 编排配置
docker compose config
```

按改动范围运行验证；改 API、调度、规则或持久化逻辑时必须运行 `pytest`，改前端时必须运行前端测试与构建。

## 修改约束

- Python 3.11+；遵循 `pyproject.toml` 的类型与 Ruff 规则。新业务行为或缺陷修复应补回归测试。
- 前端 API 数据必须经 `frontend/src/api/schemas.ts` 的 Zod schema 校验；保留无障碍语义，并遵循 `frontend/DESIGN.md`，不要引入新的 CSS 框架。
- 不得在日志、API 响应或提交内容中暴露密钥。不要提交 `.env`、虚拟环境、`node_modules`、构建产物或 SQLite 数据库。
- 不要为通过测试而删除用户可见功能，也不要无测试地削弱轮询、规则或告警行为。
- Docker Web 入口为 `54002:8080`；Nginx 将 `/api` 和 `/health` 转发到 `backend:8000`。修改端口或代理时同步 `docker-compose.yml`、`frontend/docker/nginx.conf` 与 `README.md`。
- 本地前端没有 Vite proxy；联调时通过 `VITE_API_BASE_URL` 指向后端。
- 面向用户的 README 内容使用中文；代码注释与 API 契约沿用现有英文风格。
