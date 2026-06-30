# stock-data-monitor draft

status: awaiting-approval
intent: CLEAR
size: Architecture/bootstrap
user_request: "从零建一个股票数据监控，要有一个网页配置台；对于任何一个股票标的，需要从 yfinance binance 合约 hyperliquid合约拿到最新价格；对每个标的可以配置支撑和阻力，当盈亏比大于某个数值或距离支撑位比例小于某个数值或突破阻力位时通过 telegram bot 往频道发送消息"

## Components ledger
- C1 Web configuration console: outcome = operators can create/edit/delete monitored instruments, per-source symbol mappings, support/resistance, thresholds, Telegram config/status; status = proposed; evidence = user request + empty workspace.
- C2 Price ingestion adapters: outcome = fetch latest price for each configured instrument from yfinance, Binance futures, Hyperliquid perps; status = proposed; evidence = Context7 docs for yfinance, Binance futures connector, Hyperliquid SDK.
- C3 Alert/rule engine: outcome = evaluate risk/reward, near-support percentage, resistance breakout and suppress duplicates; status = proposed; evidence = user request.
- C4 Telegram notifier: outcome = send channel messages via bot token/chat id; status = proposed; evidence = user request.
- C5 Persistence/config/runtime: outcome = durable DB-backed config + monitored state; status = open owner-decision; evidence = from-zero workspace.
- C6 Agent-executed QA/deployment: outcome = automated tests plus runnable local service; status = open owner-decision; evidence = from-zero workspace.

## Facts found
- Workspace /opt/ocode/wavemonitor is effectively empty except .codegraph/. No product code or git repo detected from directory listing. .codegraph exists but no codegraph tools are available in this session; use normal tools.
- yfinance docs show `yf.Ticker("MSFT")`, `history(...)`, `yf.download([...])`, and `dat.live()` websocket-style live data. For reliable latest quotes in a monitor, plan should prefer a poller using `Ticker.fast_info` if worker verifies installed API, falling back to `history(period="1d", interval="1m")`/download last close when fast quote is absent.
- Binance futures connector docs: USD-M mark price uses `/fapi/v1/premiumIndex` via `client.mark_price("BTCUSDT")`, returning `markPrice`, `indexPrice`, funding fields, and `time`. Websocket streams can subscribe to lowercase `<symbol>@markPrice@1s`; docs examples also show COIN-M `CMFuturesWebsocketClient` but this product should default to USDT-M unless user chooses otherwise.
- Hyperliquid Python SDK docs: `from hyperliquid.info import Info`; `Info().all_mids()` returns dict `{ BTC: "float string", ... }` for actively traded perp coins; websocket `subscribe({"type":"activeAssetCtx", "coin":"BTC"}, callback)` for perp.

## Candidate defaults
- Stack default: Python backend because all three data sources have Python SDK/doc support; FastAPI + SQLite + SQLAlchemy/SQLModel/Alembic + simple server-rendered or lightweight web UI. This is cross-cutting, so ask owner.
- Runtime default: polling MVP rather than websocket-first; every 15-30 seconds configurable. Websocket can be a later optimization. This is defensible from simplicity/reliability.
- Binance default: USD-M USDT perpetual mark price, symbol like BTCUSDT. Ask if COIN-M is required because request says 合约 but not type.
- Alert semantics default: risk/reward ratio for long setup = `(nearest_resistance - current_price) / (current_price - nearest_support)` when current price is above support and below resistance; near-support = `(current_price - nearest_support) / current_price <= threshold`; breakout = current price crosses from <= resistance to > resistance. Ask because formula affects product behavior.
- Telegram default: user supplies bot token and channel/chat ID in environment variables, web UI can test/send status but not store token in plain DB unless user chooses DB storage. Ask if acceptable because config surface/security.

## Decisions from user
- Product stack/runtime: Docker + Python backend + Node frontend.
- Alert semantics: Long-only default. Risk/reward = `(nearest_resistance - current_price) / (current_price - nearest_support)` when support < current < resistance; near-support and resistance-breakout interpreted from long perspective.
- Binance futures: contract type selectable per symbol/config; support at least USD-M and COIN-M in data model/adapters.
- Telegram credentials: bot token and target channel/chat id from environment variables, not stored in database; UI may expose status/test action only.
- Test strategy: TDD. Agent-executed QA remains mandatory.

## Approval gate
pending_action: write .omo/plans/stock-data-monitor.md after explicit user approval
approach: Build a Dockerized full-stack monitoring app from zero: Python FastAPI backend with DB-backed configuration and background polling/rule engine; Node frontend configuration console; adapters for yfinance, Binance USD-M/COIN-M mark/latest prices, Hyperliquid all mids; Telegram notifier using environment credentials; TDD-first implementation and final automated QA.
