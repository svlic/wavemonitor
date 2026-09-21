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
- `docs/adr/`：架构决策、历史背景与状态；`docs/adr/README.md` 为索引
- `README.md`、`.env.example`：运行、部署、环境变量

## 开发环境

项目标准初始化入口为根目录的 `.agents/setup`，同时适用于 Amp Orbs 与持久化 Linux Runner。脚本只写入仓库内的 `.venv`、`frontend/node_modules` 及其状态标记，不创建 `.env`、不写入密钥、不启动服务，也不使用 `sudo`。

| 范围 | 要求 | 依赖管理 |
| --- | --- | --- |
| 后端 | Python 3.11+；SQLite 由 Python 提供，无需独立数据库服务 | `.venv` + `pyproject.toml` 的 `test` extra |
| 前端 | 锁文件支持的 Node.js 20.19+、22.12+ 或 24+；npm | `frontend/package-lock.json` + `npm ci` |
| 部署检查 | Docker 24+、Docker Compose v2 | 仅编排、代理或容器构建相关任务需要 |

### Environment Initialization

- 开始开发任务前先检查所需命令与项目依赖；环境未准备好或依赖清单有变化时，从项目根目录执行 `.agents/setup`，不要用全局 Python 包代替项目虚拟环境。
- `.agents/setup` 必须保持非交互、幂等且可在干净 Orb 和已配置的持久化 Runner 上重复运行。已满足要求时应复用现有依赖，避免不必要的重复安装。
- 初始化失败时，先调查实际错误并在安全且已获授权的范围内修复，再继续开发。不得因缺少工具或依赖而跳过构建、测试或验证。
- 脚本不会擅自安装系统运行时。缺少兼容的 Python、Node.js、npm 或 Python `venv` 模块时，应给出明确错误；涉及 `sudo`、系统级包或共享运行时变更必须先获得用户授权。
- 本地开发和测试无需复制 `.env.example`：SQLite 与可选外部集成都有安全默认值。只有实际联调需要配置时才创建未跟踪的 `.env`，且绝不写入或提交真实密钥。

### Automatic Environment Recovery

后续任务遇到命令缺失、依赖缺失、版本不兼容、PATH 错误或环境损坏时：

1. 根据失败输出定位根因，区分项目环境、应用代码和外部服务问题。
2. 优先使用项目既有方式修复：后端使用 `.venv` 与 `pyproject.toml`，前端使用 npm 锁文件；先按需重新执行 `.agents/setup`。
3. 在安全且已获授权时主动修复环境，然后重新执行原先失败的命令；不得修改业务逻辑、删除测试或降低检查标准来绕过环境问题。
4. 无法安全自动修复时，明确报告阻塞原因、未执行的验证以及所需权限或外部措施。只报告实际执行成功的命令。

### Continuous Setup Maintenance

- 新发现且干净开发环境普遍需要的依赖，应在当前任务中将已验证的安装或配置同步到 `.agents/setup`；必要时也更新本节的工具链与验证命令。
- 更新 setup 后须检查 Bash 语法、可执行位，并至少连续执行两次以验证冷/热路径和幂等性。新增逻辑必须遵循现有版本与包管理方式，不得与共享环境冲突。
- 仅当前 Runner 特有的代理、PATH、权限或系统故障不得写入项目脚本。系统权限、生产服务、敏感信息和其他高风险操作仍需事先授权。
- 删除过时、重复或错误的 setup 逻辑前，先确认对应项目依赖确已不再需要。环境修复与 setup 维护属于正常开发任务，不应只给用户手工操作建议。

## 改动

- 行为变更或修缺陷：补回归测试。
- HTTP/契约变更：同步契约、后端、前端 Zod/client 与相关测试。
- 改变技术栈、运行时边界、持久化/数据模型、安全模型、部署方式、外部服务策略，或对性能、成本、长期维护有显著影响时：新增 ADR，并更新 `docs/adr/README.md`。
- 普通功能、局部重构和缺陷修复不单独建 ADR，除非它们改变已有架构决策。
- 改变已有决策时不覆盖原 ADR；新增 ADR 说明取代关系，并同步旧 ADR 状态与索引。实现不得无记录地偏离已接受 ADR。
- ADR 使用下一个四位编号，正文为中文，至少记录状态、背景、决策、结果/权衡、替代方案与依据；事实和推断必须明确区分。
- 前端：入站 API 数据必须经 Zod 校验；保留无障碍语义。
- 端口或代理变更：同步 `docker-compose.yml`、`frontend/docker/nginx.conf`、`README.md`。
- 不暴露密钥；不提交 `.env`、构建产物、SQLite。
- 用户文档中文；代码注释与 API 契约英文。

## 构建与验证

初始化脚本自身：

```bash
bash -n .agents/setup
test -x .agents/setup
.agents/setup
.agents/setup            # setup 有改动时再次执行，验证幂等性
```

按改动范围使用项目内工具执行：

```bash
.venv/bin/pytest
.venv/bin/ruff check backend/src backend/tests
.venv/bin/vulture
(cd frontend && npm test && npm run build)  # build 包含 TypeScript noEmit 类型检查
docker compose config                         # 仅编排、代理或部署配置相关改动
```

Python 业务逻辑必须执行 `pytest`；前端改动必须执行测试与构建。前端当前没有单独的 Lint 脚本，类型检查由 `npm run build` 中的 `tsc --noEmit` 执行。完成任务时应报告实际命令与结果；环境导致失败时先修复并重跑，未执行或未通过的项目必须明确说明原因。
