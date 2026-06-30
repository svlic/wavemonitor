---
slug: stock-data-monitor-build
status: drafting
intent: clear
pending-action: write .omo/plans/stock-data-monitor-build.md
approach: Dockerized full-stack monitor: Python FastAPI backend, Node frontend config console, DB-backed instruments/rules/state, polling price adapters for yfinance/Binance USD-M+COIN-M/Hyperliquid, Long-only rule engine, Telegram env-based notifier, TDD-first implementation and agent-executed QA.
---

# Draft: stock-data-monitor-build

## Components (topology ledger)
| id | outcome (one line) | status | evidence path |
| --- | --- | --- | --- |
| C1 | Node frontend web console manages instruments, symbol mappings, thresholds, status, and Telegram test/status. | active | /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:8 |
| C2 | Python FastAPI backend exposes CRUD/status/test APIs and serves scheduler/runtime health. | active | /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:29 |
| C3 | Price adapters fetch latest prices from yfinance, Binance USD-M/COIN-M futures, and Hyperliquid perps using Decimal-safe parsing. | active | /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:16 |
| C4 | Long-only rule engine evaluates risk/reward, near-support, and resistance-breakout with dedupe/cooldown state. | active | /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:29 |
| C5 | Telegram notifier sends channel alerts with credentials from environment variables only. | active | /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:33 |
| C6 | Docker compose runtime and TDD/QA evidence prove the app runs locally without manual intervention. | active | /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:29 |

## Open assumptions (announced defaults)
| assumption | adopted default | rationale | reversible? |
| --- | --- | --- | --- |
| Backend DB | SQLite volume in Docker for MVP, with SQLAlchemy models keeping PostgreSQL migration straightforward. | Empty project; local monitor needs low-ops persistence. | Yes |
| Ingestion mode | Polling-first scheduler, not websocket-first. | yfinance websocket is less stable; polling is simpler and testable. | Yes |
| Poll interval | Global env/config default 30s, per-instrument override optional only if cheap. | Avoid aggressive yfinance/Yahoo polling. | Yes |
| Frontend stack | Vite + React + TypeScript. | User requested Node frontend; this is standard, testable, and Docker-friendly. | Yes |
| Price precision | Use Decimal in backend rule evaluation and persisted prices. | Hyperliquid and exchange APIs return string prices; float can misfire alerts. | No for correctness |
| Telegram credentials | TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars only. | User chose env storage; reduces secret exposure. | Yes, but out of scope |

## Findings (cited - path:lines)
- Workspace is empty of product code except .omo/.codegraph; no git repo or stack constraints exist: /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:16
- yfinance supports Ticker usage and history/download; plan requires worker to verify `fast_info` in installed version and fallback to 1m history/download: /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:18
- Binance futures connector docs include mark price/premium index and websocket streams; user requires USD-M/COIN-M selectable: /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:19
- Hyperliquid SDK `Info().all_mids()` returns string prices keyed by perp coin; use Decimal parsing: /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:20
- User decisions: Docker + Python backend + Node frontend, Long-only, Binance contract type selectable, Telegram env credentials, TDD: /opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:29

## Decisions (with rationale)
- Use FastAPI for backend APIs and background lifecycle because Python fits all data-source SDKs and is simple to test with pytest/TestClient.
- Use Vite React TypeScript for the Node frontend because it provides a small, typed configuration UI with fast tests/builds.
- Use Docker compose with `backend`, `frontend`, and persistent `data` volume; no external DB service in MVP.
- Implement polling adapters behind a common interface returning source, symbol, Decimal price, timestamp, and raw payload summary.
- Evaluate alert rules per source price and persist last rule state to prevent duplicate alerts until condition resets or cooldown expires.
- Keep Telegram secrets out of the DB; API exposes readiness/test-send without echoing secrets.

## Scope IN
- Create full project structure from zero.
- Backend FastAPI app, SQLAlchemy/SQLModel persistence, migrations or deterministic schema init.
- CRUD APIs for instruments, source mappings, support/resistance, thresholds, enabled rules, and status.
- Price adapters for yfinance, Binance USD-M, Binance COIN-M, Hyperliquid.
- Scheduler/poller and rule engine with dedupe/cooldown.
- Telegram notifier using environment variables.
- Node frontend configuration console.
- Dockerfiles, docker-compose, env example without real secrets.
- TDD tests and final agent-executed QA evidence.

## Scope OUT (Must NOT have)
- No trading/order placement.
- No user authentication/multi-user roles unless explicitly requested later.
- No storing Telegram bot token or chat id in the database.
- No production deployment, cloud infra, or CI setup unless explicitly requested later.
- No websocket-first implementation in MVP; may leave documented extension points only.
- No fake live-price tests that hit real external APIs in unit tests; use mocks for deterministic tests and optional smoke script for live checks.

## Open questions
- None blocking. User approved the recorded owner decisions.

## Approval gate
status: approved
approved_action: write .omo/plans/stock-data-monitor-build.md
approval_source: user replied "批准".
