# Architecture Decision Records

本目录记录 WaveMonitor 的重要架构决策。现有 ADR 根据 2026-06-30 至
2026-09-20 的 Git 历史重建，并由项目所有者补充部分原始背景。

## 状态

- **已接受**：当前主线仍遵循该决策。
- **已接受（实现待对齐）**：决策已确认，但当前实现仍存在已知偏差。
- **已取代**：该方案曾进入主线，后来被其他方案替代或迁出本仓库。
- **待复审**：当前仍在使用，但已知条件变化时需要重新评估。

## 索引

| ADR | 标题 | 状态 |
| --- | --- | --- |
| [0001](0001-single-instance-full-stack-and-polling.md) | 采用单实例全栈与轮询架构 | 已接受 |
| [0002](0002-market-data-adapters-and-provider-catalogs.md) | 通过适配器和供应商目录统一行情源 | 已接受 |
| [0003](0003-instrument-owned-source-mappings.md) | 行情源映射归属于监控标的 | 已接受 |
| [0004](0004-optional-shared-password-authentication.md) | 为公网部署提供可选共享密码认证 | 待复审 |
| [0005](0005-application-managed-sqlite-migrations.md) | 由应用启动流程管理 SQLite 迁移 | 已接受 |
| [0006](0006-multi-level-price-rules.md) | 使用多级价格梯和固定回撤规则 | 已接受 |
| [0007](0007-persistent-alert-state-machine.md) | 使用持久化状态机定义告警与重试 | 已接受（实现待对齐） |
| [0008](0008-in-process-monitoring-lifecycle.md) | 在 FastAPI 生命周期内运行监控调度器 | 已接受 |
| [0009](0009-frontend-api-validation-and-polling.md) | 在前端 API 边界校验数据并定时刷新 | 已接受 |
| [0010](0010-cloudflare-workers-experiment.md) | Cloudflare Workers 与 D1 部署实验 | 已取代 |
| [0011](0011-in-memory-latest-price-state.md) | 将最新行情状态保存在进程内存 | 已接受 |
| [0012](0012-avoid-redundant-thin-layers.md) | 避免没有独立职责的薄抽象层 | 已接受 |

## 重建说明

每份 ADR 的“历史依据”列出相关提交。“已确认背景”来自 Git 中的项目文档、
提交说明或项目所有者答复；“历史推断”只用于解释证据不足的部分，不代表当时
明确讨论或验证过。重建 ADR 不以当前代码状态反推历史方案必然成功。
