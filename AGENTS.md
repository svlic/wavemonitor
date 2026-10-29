# WaveMonitor

行情轮询与告警。后端 FastAPI + SQLModel + SQLite；前端 React + TypeScript + Vite。

## 代码与文档

- 后端：`backend/src/wavemonitor_backend/`；测试：`backend/tests/`。
- 前端：`frontend/src/`；测试：`frontend/tests/`；API 校验：`frontend/src/api/schemas.ts`。
- API 以当前代码与 `backend/API_CONTRACT.md` 为准；UI 遵循 `frontend/DESIGN.md`，不引入新 CSS 框架。
- 架构决策：`docs/adr/README.md`；运行、部署与环境变量：`README.md`、`.env.example`。

## 开发环境

- Python 3.11+；Node.js 20.19+、22.12+ 或 24+；npm。仅部署相关任务需要 Docker / Compose v2。
- 开发前检查依赖；缺失、损坏或依赖清单变化时，在根目录运行 `.agents/setup`。后端使用 `.venv`（`pyproject.toml` 的 `test` extra），前端使用 npm 锁文件，不用全局 Python 包替代。
- 环境故障先诊断、修复并重跑失败命令，不得降低检查标准；系统级或共享运行时变更须先获授权。
- 本地开发和测试无需 `.env` 或独立数据库服务；不提交密钥、`.env`、SQLite 或构建产物。
- 维护 `.agents/setup` 时保持非交互、幂等、复用已有依赖；不使用 sudo、不创建 `.env`、不启动服务。通用环境修复同步到脚本，Runner 特有故障不写入。

## 改动

- 行为变更或修缺陷：补回归测试。
- HTTP/契约变更：同步契约、后端、前端 Zod/client 与相关测试。
- 前端：入站 API 数据必须经 Zod 校验；保留无障碍语义。
- 端口或代理变更：按影响同步 `docker-compose.yml`、`frontend/docker/nginx.conf` 与 `README.md`。Compose 使用预构建 GHCR 镜像，不在部署端构建。
- 架构性变更（技术栈、运行时边界、持久化/数据模型、安全、部署、外部服务策略或显著性能/成本/维护影响）新增 ADR；普通功能、局部重构和修复无需单独记录，除非改变已有决策。
- ADR 用下一个四位编号，中文记录状态、背景、决策、权衡、替代方案与依据，区分事实与推断。取代旧决策时保留原文，更新旧 ADR 状态、取代关系及索引 `docs/adr/README.md`。
- 用户文档中文；代码注释与 API 契约英文。

## 验证

在根目录按改动范围执行：

| 范围 | 命令 |
| --- | --- |
| Python | `.venv/bin/pytest`；`.venv/bin/ruff check backend/src backend/tests`；`.venv/bin/vulture` |
| 前端 | `npm --prefix frontend test`；`npm --prefix frontend run build`（含 TypeScript 类型检查） |
| 编排、代理或部署配置 | `docker compose config` |
| 初始化脚本 | `bash -n .agents/setup`；`test -x .agents/setup`；连续执行两次 `.agents/setup` |

Python 业务逻辑必须跑 pytest；前端改动必须跑测试和构建。报告实际执行结果及未通过或未执行的原因。
