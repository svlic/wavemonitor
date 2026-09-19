# ADR 0002：通过适配器和供应商目录统一行情源

- **状态**：已接受
- **决策时间**：2026-06 至 2026-09

## 背景

系统需要同时支持 yfinance、Binance USD-M/COIN-M 和 Hyperliquid。不同供应商的
symbol、市场类型、返回格式和代理配置并不一致。生产部署还实际遇到过 Binance
HTTP 451，因此需要网络降级和代理能力。

初期 symbol 输入依赖简单后缀拼接，无法可靠反映交易所真实可用合约；不同 SDK
也暴露了 float、Pandas 值、HIP-3 dex 前缀等不一致数据形态。

## 决策

- 通过统一价格适配器协议向监控调度器返回规范化的价格结果或类型化错误。
- 在 API 层限制合法的 provider/market-type 组合。
- Symbol 查询优先读取供应商真实目录：
  - Binance `exchange_info`；
  - Hyperliquid `all_mids` 和 `perp_dexs`；
  - yfinance Search。
- Binance 目录不可用时，允许回退为规范化的手工 symbol，确保用户仍可配置标的。
- 统一使用 `WAVEMONITOR_SOCKS5_PROXY` 为所有行情查询和轮询配置 SOCKS5/SOCKS5H
  代理；推荐 SOCKS5H 以便 DNS 也经过代理。
- 外部客户端延迟创建，避免模块导入时发生网络或 SDK 初始化副作用。

## 结果

### 正面影响

- 规则引擎和调度器不依赖具体 SDK 返回结构。
- 前端可基于供应商真实目录辅助输入，同时保留手工输入作为降级路径。
- 一个代理配置覆盖三个供应商，适配受限网络环境。

### 负面影响和限制

- 回退生成的 symbol 未经过供应商确认，可能保存无效映射。
- SDK 差异仍由适配器层承担，供应商升级可能造成解析回归。
- 统一代理意味着不能为不同供应商分别配置出口。

## 已考虑的替代方案

- **仅通过字符串拼接生成 symbol**：被真实供应商目录取代，仅保留故障回退。
- **仅代理 Binance HTTPS**：在 `484cfd2` 引入，后被覆盖所有行情源的 SOCKS5
  配置取代。
- **直接调用供应商 HTTP API、移除 SDK**：当时未评估。

## 历史依据

- `bf41eb0`：以真实供应商目录替代后缀拼接。
- `986fc8c`：支持 Hyperliquid HIP-3 dex 前缀 symbol。
- `da835fc`：兼容 yfinance float 和 Pandas Close 数据。
- `6a4c146`：Binance 目录不可用时回退到规范化 symbol。
- `484cfd2`：增加 Binance 专用 HTTPS 代理以应对 HTTP 451。
- `4ce92e7`：改为覆盖所有行情源的 SOCKS5 代理。
