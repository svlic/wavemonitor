# ADR 0009：在前端 API 边界校验数据并定时刷新

- **状态**：已接受
- **决策时间**：2026-06 至 2026-09

## 背景

前端展示运行状态、最新价格、告警和可编辑 Instrument。后端响应可能随契约演进，浏览器
缓存也可能使操作员看到旧状态。项目没有引入通用 server-state 库。

项目曾建立一个全局 `instrumentRevision` store，让配置修改后 Dashboard 立即刷新；该
store 和单用途 polling hook 后来在消融式重构中删除，页面改为直接拥有刷新逻辑。

## 决策

- 所有入站 API 数据必须经过 `frontend/src/api/schemas.ts` 中的 Zod schema 校验。
- API client 负责 HTTP 错误、FastAPI 422 detail 和响应 schema 错误的统一转换。
- API 请求使用 `cache: no-store`。
- Dashboard 自行并行加载 runtime、instrument 和 latest-price 数据，并每 120 秒刷新。
- 页面保留手动刷新；当前不维护跨路由全局 server-state store。
- 不因本 ADR 排除未来采用 React Query、SWR 或同类库；只有实际一致性或缓存需求出现时
  再评估。

## 结果

### 正面影响

- 后端契约漂移在 API 边界快速暴露，不会把未知对象直接传入组件。
- 数据所有权直接位于消费页面，减少一次性 wrapper、hook 和发布订阅代码。
- 周期刷新与后端默认轮询周期一致，模型简单。

### 负面影响和限制

- 配置页面返回 Dashboard 后，数据最多可能陈旧一个刷新周期；项目所有者确认可接受。
- 不同页面会分别请求相同资源，没有共享缓存和请求去重。
- Zod schema 与后端 Pydantic schema 需要人工同步。

## 被替代的方案

- **自定义 `instrumentRevision` 外部 store**：曾用于跨页面立即刷新，后作为死的冗余层
  删除。
- **单用途 `usePollingRefresh` hook**：内联为 Dashboard 自有 interval。

## 历史依据

- `dbfbecd`：前端 Zod/client 与后端契约对齐。
- `2da1bdf`、`1947304`：引入 revision store 和配置后即时刷新。
- `0391a79`：抽离 API schema 并禁用 fetch cache。
- `40c8cfd`：删除 revision store 和单用途 polling hook。
- `bb2c95f`：继续删除只转发数据的页面 wrapper。
- 项目所有者确认：两分钟内的陈旧可接受，并未明确排除 server-state 库。
