# AGENTS.md — WaveMonitor 协作者指南

面向在本仓库中工作的 AI 与自动化工具。人类开发者也可作速查。

## 项目是什么

WaveMonitor：轮询多数据源价格 → 规则判断（支撑/阻力等）→ 持久化告警 → 可选 Telegram 通知。带 React 管理界面与 Docker Compose 一键部署。

## 仓库布局

| 路径 | 职责 |
| --- | --- |
| `backend/src/wavemonitor_backend/` | FastAPI 应用、调度、适配器、规则、通知 |
| `backend/tests/` | pytest；改 API 或业务逻辑须跑通 |
| `frontend/src/` | React 页面：`Dashboard`、`instruments/*` |
| `frontend/DESIGN.md` | 前端设计 token；改 UI 须遵守 |
| `backend/API_CONTRACT.md` | HTTP 路由契约 |
| `docker-compose.yml` | 生产式本地/部署编排；**Web 宿主机端口 54002** |

## 常用命令

```bash
# 后端测试（仓库根目录）
pytest

# 前端
cd frontend && npm test && npm run build

# Docker
docker compose up --build
```

## 编码约定

### Python（后端）

- Python 3.11+，类型注解与 ruff 规则见 `pyproject.toml`
- 新行为优先补测试；勿用 `as any` 式绕过（Python 侧避免无类型裸字典扩散）
- 密钥不得写入日志或 API 响应；Telegram 相关已做脱敏模式

### TypeScript（前端）

- API 响应经 `zod` 校验（`frontend/src/api/client.ts`）
- 路由：`wouter`；测试使用 `@testing-library/react`，勿破坏现有 `aria-*` 与英文文案（测试断言依赖）
- 样式：全局 `styles.css` + `DESIGN.md` token；勿引入未讨论的 CSS 框架

## 修改时注意

1. **Compose 端口**：对外 Web 为 `54002:8080`（frontend 容器 Nginx 8080）。改端口须同步 `README.md`。
2. **数据库**：Compose 使用命名卷；本地开发常用文件 SQLite。
3. **前端 API**：生产构建通过 Nginx 将 `/api` 代理到 `backend:8000`；本地 Vite 需代理或直连后端。
4. **计划文档**：`.omo/plans/` 为历史规划，以当前代码与 `API_CONTRACT.md` 为准。

## 不要做的事

- 不要提交 `.env`、`.venv`、`node_modules`、`*.sqlite3`、`.codegraph/`
- 不要在没有测试的情况下删除或弱化告警/轮询逻辑
- 不要为通过 Lighthouse/测试而删除用户可见功能（见 `frontend` skill perfection 原则）

## 文档语言

- 用户面向说明：`README.md` 使用**中文**
- 代码注释与 API 契约：保持现有英文风格即可，除非任务明确要求翻译