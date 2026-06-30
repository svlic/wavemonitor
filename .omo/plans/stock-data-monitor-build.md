# stock-data-monitor-build - Work Plan

## TL;DR (For humans)

**What you'll get:** A Dockerized stock/crypto monitoring app with a Python backend, Node web configuration console, persistent instrument/rule settings, live-ish price polling from yfinance, Binance futures, and Hyperliquid, and Telegram channel alerts when configured Long-only support/resistance conditions trigger.

**Why this approach:** Python is the reliable integration point for the market-data SDKs, while a Node frontend gives a proper configuration console. Polling is the first implementation because it is deterministic, testable, and safer for yfinance than websocket-first streaming.

**What it will NOT do:** It will not place trades, manage exchange accounts, store Telegram secrets in the database, or build production cloud infrastructure. It will not use live external APIs in unit tests.

**Effort:** Large
**Risk:** Medium - the main risk is external market-data API behavior and symbol differences across yfinance, Binance USD-M/COIN-M, and Hyperliquid.
**Decisions to sanity-check:** SQLite MVP storage, polling-first runtime, Vite React TypeScript frontend, Long-only alert semantics, Telegram credentials via environment variables.

Your next move: choose whether to start implementation from this plan now, or run a high-accuracy plan review first. Full execution detail follows below.

---

> TL;DR (machine): Large/Medium plan to build Docker + FastAPI + Vite React monitoring app with TDD, adapters, rules, Telegram, and full QA.

## Scope
### Must have
- Create a from-zero Dockerized project in `/opt/ocode/wavemonitor` without relying on any existing product code.
- Python FastAPI backend with typed configuration, persistent SQLite storage, deterministic schema initialization or migrations, API docs, health endpoints, and background polling lifecycle.
- Node frontend configuration console for instruments, per-source symbol mappings, support/resistance, thresholds, enable flags, runtime status, and Telegram readiness/test.
- Data source adapters for yfinance, Binance USD-M futures, Binance COIN-M futures, and Hyperliquid perpetuals.
- Long-only alert rule evaluation:
  - risk/reward = `(nearest_resistance - current_price) / (current_price - nearest_support)` only when `support < current_price < resistance`.
  - near support = `(current_price - nearest_support) / current_price <= threshold`.
  - resistance breakout = previous price `<= resistance` and current price `> resistance`.
- Duplicate suppression/cooldown state so persistent conditions do not spam Telegram.
- Telegram notification sender using `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables only.
- TDD-first tests for backend rules, persistence/API behavior, mocked adapters, mocked Telegram, frontend behavior, and Docker smoke checks.
- Agent-executed evidence under `.omo/evidence/` for every task.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Must not implement trading, order placement, exchange auth, portfolio tracking, or PnL accounting beyond configured risk/reward math.
- Must not store Telegram bot token or channel/chat id in the DB or expose their raw values through APIs/UI.
- Must not build user login, roles, multi-tenant accounts, cloud deployment, or CI unless requested later.
- Must not make unit tests depend on real yfinance/Binance/Hyperliquid/Telegram network calls.
- Must not use floats for alert-rule arithmetic; parse price/threshold values as Decimal or exact numeric equivalents in the backend.
- Must not add websocket-first ingestion in the MVP; extension seams are acceptable but inactive websocket services are not.
- Must not overwrite `.omo/` planning artifacts except adding task evidence under `.omo/evidence/`.

## Definitions And Contracts
- Latest price semantics:
  - yfinance: use `Ticker.fast_info.last_price` when available; fallback to latest valid 1-minute history/download close; record which path produced the price.
  - Binance USD-M: use USD-M futures symbol price/mark-price semantics consistently per adapter config; default to mark price for alerts when both mark and last trade are available.
  - Binance COIN-M: use COIN-M futures symbol price/mark-price semantics consistently per adapter config; default to mark price for alerts when both mark and last trade are available.
  - Hyperliquid: use `Info().all_mids()` mid price for perpetual coin keys.
- Instrument identity: persisted instruments have a stable internal ID and one or more source mappings; provider + market type + symbol identify a source mapping, not the instrument by itself.
- Support/resistance cardinality: MVP stores exactly one support and one resistance per instrument. Multiple level lists and automatic support/resistance detection are out of scope.
- Threshold units: thresholds are stored as decimal fractions, e.g. `0.02` means 2 percent. UI may display percentages, but API and backend normalize to fractions.
- Valid rule range: risk/reward is computed only when `support < current_price < resistance` and `current_price > 0`. Otherwise the rule returns a typed non-alert reason.
- Below-support behavior: if `current_price < support`, near-support may be reported as below-support status but must not trigger the standard near-support alert unless the plan is explicitly changed later.
- Breakout behavior: no breakout on the first observation; breakout triggers only when `previous_price <= resistance` and `current_price > resistance`; remaining above resistance must not repeatedly alert.
- Duplicate policy: near-support and risk/reward alerts fire once when entering the triggering state, then reset after leaving the state or after an explicit cooldown expires. Breakout is transition-based and non-repeating until price returns to/below resistance.
- Telegram env names: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Missing credentials must keep the app healthy with Telegram readiness false and sends disabled.
- Backend API contract MVP:
  - `GET /health` returns HTTP 200 with status.
  - `GET /api/instruments`, `POST /api/instruments`, `PUT /api/instruments/{id}`, `DELETE /api/instruments/{id}` manage instruments and source mappings.
  - `GET /api/instruments/{id}/status` returns latest source prices/errors and alert state.
  - `GET /api/alerts` returns recent alert events.
  - `GET /api/runtime` returns scheduler/provider/Telegram readiness.
  - `POST /api/telegram/test` sends or simulates a Telegram test message when credentials are present and returns redacted status.
- Docker contract: compose includes backend and frontend services, a persistent SQLite data volume, explicit ports, backend healthcheck, frontend-to-backend URL wiring, and env injection from `.env`/environment without real secrets.
- Frontend MVP screens: instrument list, create/edit form, source mapping rows, rule threshold fields, latest status/dashboard, recent alerts/errors, Telegram readiness/test. No charts, auth, portfolio, or trading screens.

## QA Matrix
- Rule engine: exact Decimal cases for risk/reward `support=90`, `price=100`, `resistance=130` => `3`; near-support true for `98/100/0.02`; near-support false for `97/100/0.02`; breakout previous `100`, current `111`, resistance `110` true; first observation false; repeated above-resistance false.
- Provider adapters: mocked normalized latest price tests for yfinance `AAPL`, Binance USD-M `BTCUSDT`, Binance COIN-M representative symbol such as `BTCUSD_PERP`, and Hyperliquid `BTC`; mocked timeout, HTTP 429/rate-limit, invalid symbol, and malformed payload tests.
- API: validation tests for missing provider, unsupported provider, invalid symbol, thresholds outside allowed range, `support >= resistance`, no source mappings, and status when no observations exist.
- Scheduler: polls enabled instruments, skips disabled instruments, continues after one source fails, records source error, updates last price/timestamp, and dedupes repeated alerts.
- Telegram: missing env readiness false, successful mocked send, failed Telegram API response, token/chat id absent from logs/API/DB, and no send attempt when credentials are missing.
- Persistence: create instrument through API, restart backend/container or recreate app with same SQLite file, verify instrument persists and Telegram secrets are still absent.
- Frontend: automated tests for create/edit/delete/disable instrument, source selection, threshold validation, status/error rendering, Telegram disabled state, and test-send flow with mocked backend.
- Docker: `docker compose up --build -d`, `curl -fsS http://localhost:8000/health`, frontend HTTP root responds, backend can write SQLite volume, missing Telegram env keeps health OK/readiness false, and compose logs show no crash loop.
- Network discipline: default tests block or mock external network; optional live provider smoke runs only when `RUN_LIVE_SMOKE=1`.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD with backend pytest/httpx or TestClient, frontend Vitest/Testing Library, lint/typecheck/build gates, Docker compose smoke checks.
- Evidence: `.omo/evidence/task-<N>-stock-data-monitor-build.<ext>` per todo, with command output and assertions.
- Backend unit tests must run with mocked external adapters and mocked Telegram HTTP client.
- Frontend tests must verify rendered forms, validation, API calls with mocked fetch, and status/test interactions.
- Integration tests must start the backend against a temp SQLite DB and verify CRUD/rule/status flows.
- Final smoke must build containers, start compose, call backend health/API, and if frontend is served separately verify the page loads.

## Execution strategy
### Parallel execution waves
- Wave 1 establishes project skeleton, contracts, and failing tests. Backend and frontend skeletons can proceed in parallel after directory layout exists.
- Wave 2 implements backend domain/persistence and frontend API client/UI foundations. These can parallelize if OpenAPI/API contracts are stable.
- Wave 3 implements adapters, scheduler, rule engine, Telegram notifier, and frontend rule/status surfaces. Adapter implementation can parallelize with frontend UI once API shapes are fixed.
- Wave 4 integrates Docker compose, end-to-end smoke paths, documentation-in-code/env examples, and final verification.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 2, 3, 4, 5 | none |
| 2 | 1 | 4, 5, 6, 7, 8, 9 | 3 |
| 3 | 1 | 10, 11 | 2 |
| 4 | 2 | 6, 7, 8, 9 | 5, 10 |
| 5 | 2 | 6, 7, 8, 9, 11 | 4, 10 |
| 6 | 4, 5 | 8, 9, 12 | 7, 10 |
| 7 | 4, 5 | 8, 9, 12 | 6, 10 |
| 8 | 6, 7 | 9, 12 | 11 |
| 9 | 6, 7, 8 | 12 | 11 |
| 10 | 3, 4 | 11, 12 | 5, 6, 7 |
| 11 | 10, 5 | 12 | 8, 9 |
| 12 | 8, 9, 11 | final verification | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. Bootstrap repository layout, toolchains, and failing smoke tests
  What to do / Must NOT do: Create backend/frontend/docker directory layout, Python project config, Node project config, `.env.example`, `.gitignore`, evidence directory, initial failing tests that define expected health endpoints and frontend load behavior, and a checked-in backend/frontend API contract stub matching the Backend API contract section. Must not add real secrets or external API calls.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 2, 3, 4, 5
  References (executor has NO interview context - be exhaustive): `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor-build.md` decisions and scope; original user request in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:6`.
  Acceptance criteria (agent-executable): `pytest` discovers backend tests; `npm test` or `npm run test` discovers frontend tests; initial intended tests fail before implementation and pass by task end for skeleton behavior; no product code outside planned directories except config files.
  QA scenarios (name the exact tool + invocation): happy: run backend/frontend test discovery and capture output to `.omo/evidence/task-1-stock-data-monitor-build.txt`; failure: temporarily unset expected env/default config in test context and verify app reports missing optional Telegram readiness without crash.
  Commit: N | chore(scaffold): initialize monitor project structure

- [x] 2. Define backend configuration, domain models, and Decimal-safe rule contracts with TDD
  What to do / Must NOT do: Implement typed settings, SQLAlchemy/SQLModel models or equivalent for instruments, source mappings, thresholds, price observations, alert events, and last-rule state. Add tests first for validation, Decimal parsing, invalid support/resistance, and env-only Telegram config. Must not store Telegram credentials in DB.
  Parallelization: Wave 1/2 | Blocked by: 1 | Blocks: 4, 5, 6, 7, 8, 9
  References (executor has NO interview context - be exhaustive): Long-only decisions in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:29`; Must NOT secrets rule in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor-build.md`.
  Acceptance criteria (agent-executable): backend model/settings tests pass; a schema inspection test proves no Telegram token/chat id columns exist; Decimal tests reject float-only arithmetic paths; model tests enforce exactly one support/resistance pair per instrument, thresholds as decimal fractions, and stable source mapping identity as provider + market type + symbol.
  QA scenarios (name the exact tool + invocation): happy: `pytest backend/tests/test_models.py backend/tests/test_settings.py`; failure: invalid `support >= resistance` fixture returns validation error and evidence in `.omo/evidence/task-2-stock-data-monitor-build.txt`.
  Commit: N | feat(backend): define monitor domain models

- [x] 3. Build frontend foundation and typed API contract tests
  What to do / Must NOT do: Create Vite React TypeScript app, routing/layout, API client types matching planned backend DTOs, form validation helpers, and tests for API-client error handling. Must not hard-code backend URLs except through config/env.
  Parallelization: Wave 1/2 | Blocked by: 1 | Blocks: 10, 11
  References (executor has NO interview context - be exhaustive): Node frontend decision in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:30`; UI component C1 in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor-build.md`.
  Acceptance criteria (agent-executable): `npm run typecheck`, `npm run test`, and `npm run build` pass for the frontend skeleton with mocked API tests.
  QA scenarios (name the exact tool + invocation): happy: `npm run test -- --run` and `npm run build`; failure: mocked API 500 shows a recoverable error state, evidence `.omo/evidence/task-3-stock-data-monitor-build.txt`.
  Commit: N | feat(frontend): initialize configuration console shell

- [x] 4. Implement backend CRUD/status APIs with database-backed TDD
  What to do / Must NOT do: Implement FastAPI app, DB session lifecycle, CRUD endpoints for instruments and source mappings, status endpoint, and validation responses. Must not expose raw Telegram env values.
  Parallelization: Wave 2 | Blocked by: 2 | Blocks: 6, 7, 8, 9, 10
  References (executor has NO interview context - be exhaustive): Scope IN backend/API in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor-build.md`; workspace from-zero fact in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:16`.
  Acceptance criteria (agent-executable): API tests using temp SQLite DB pass for create/list/update/delete instrument, enabled/disabled sources, validation errors, health/status, recent alerts, runtime readiness, and Telegram test endpoint redaction. Validation tests cover missing provider, unsupported provider, invalid symbol, threshold outside allowed range, `support >= resistance`, and no source mappings.
  QA scenarios (name the exact tool + invocation): happy: `pytest backend/tests/test_api_instruments.py`; failure: create instrument without any source mapping returns 422/400 as specified, evidence `.omo/evidence/task-4-stock-data-monitor-build.txt`.
  Commit: N | feat(api): add instrument configuration endpoints

- [x] 5. Implement mocked price adapter interface and concrete yfinance/Binance/Hyperliquid adapters with TDD
  What to do / Must NOT do: Define a common adapter protocol returning source, market type, symbol, Decimal price, timestamp, and raw metadata. Implement yfinance, Binance USD-M, Binance COIN-M, and Hyperliquid adapters with tests mocking SDK/client responses. Must not call live external APIs in unit tests.
  Parallelization: Wave 2 | Blocked by: 2 | Blocks: 6, 7, 8, 9
  References (executor has NO interview context - be exhaustive): yfinance finding `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:18`; Binance finding `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:19`; Hyperliquid finding `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:20`; librarian caveat that Hyperliquid string prices need Decimal.
  Acceptance criteria (agent-executable): adapter unit tests pass for normal response, missing symbol, malformed price, timeout/error mapping, HTTP 429/rate-limit mapping, yfinance `AAPL`, USD-M `BTCUSDT`, COIN-M representative symbol such as `BTCUSD_PERP`, Hyperliquid `BTC`, USD-M vs COIN-M route selection, and Hyperliquid all_mids lookup. Tests prove normalized latest price semantics match the Definitions section.
  QA scenarios (name the exact tool + invocation): happy: `pytest backend/tests/test_adapters.py`; failure: malformed price string returns a typed adapter error without crashing scheduler, evidence `.omo/evidence/task-5-stock-data-monitor-build.txt`.
  Commit: N | feat(adapters): add market data providers

- [x] 6. Implement Long-only rule engine, alert event persistence, and dedupe/cooldown with TDD
  What to do / Must NOT do: Write failing tests first for risk/reward, near-support, breakout-crossing, invalid denominator, support/resistance edge cases, source-specific evaluation, reset behavior, and cooldown/dedupe. Implement pure rule engine plus persistence integration. Must not send Telegram directly from pure rule calculation.
  Parallelization: Wave 3 | Blocked by: 4, 5 | Blocks: 8, 9, 12
  References (executor has NO interview context - be exhaustive): Alert semantics decision `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:31`; rule component C4 in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor-build.md`.
  Acceptance criteria (agent-executable): rule tests pass with Decimal exactness, including risk/reward `support=90`, `price=100`, `resistance=130` => `3`; near-support true for support `98`, price `100`, threshold `0.02`; near-support false for support `97`, price `100`, threshold `0.02`; breakout previous `100`, current `111`, resistance `110` true; first observation false; previous `111`, current `112`, resistance `110` false; repeated near-support state suppressed until reset/cooldown.
  QA scenarios (name the exact tool + invocation): happy: `pytest backend/tests/test_rules.py`; failure: price below support or equal to support does not divide by zero and returns a non-alert/invalid-state result as specified, evidence `.omo/evidence/task-6-stock-data-monitor-build.txt`.
  Commit: N | feat(rules): evaluate support resistance alerts

- [x] 7. Implement Telegram notifier and alert delivery API with mocked TDD
  What to do / Must NOT do: Implement Telegram Bot API client, message formatter, readiness endpoint, test-send endpoint, and delivery result persistence/logging. Must use env vars only and must redact secrets in logs/errors/API.
  Parallelization: Wave 3 | Blocked by: 4, 5 | Blocks: 8, 9, 12
  References (executor has NO interview context - be exhaustive): Telegram env decision `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:33`; Must NOT store credentials in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor-build.md`.
  Acceptance criteria (agent-executable): tests pass for missing env readiness false, successful mocked send, Telegram HTTP failure, redaction, and message content including instrument/source/rule/price/support/resistance.
  QA scenarios (name the exact tool + invocation): happy: `pytest backend/tests/test_telegram.py`; failure: unset `TELEGRAM_BOT_TOKEN` returns readiness false and no send attempt, evidence `.omo/evidence/task-7-stock-data-monitor-build.txt`.
  Commit: N | feat(notify): add telegram alert sender

- [x] 8. Implement polling scheduler and end-to-end backend monitoring loop with TDD
  What to do / Must NOT do: Implement background scheduler lifecycle, per-enabled-source polling, price observation writes, rule evaluation, alert event creation, Telegram delivery dispatch, and status metrics. Must keep tests deterministic with fake adapters/time/notifier.
  Parallelization: Wave 3 | Blocked by: 6, 7 | Blocks: 9, 12
  References (executor has NO interview context - be exhaustive): Polling default in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor-build.md`; adapter/rule/notifier todos 5-7.
  Acceptance criteria (agent-executable): integration tests pass for one instrument with three source mappings, all mocked prices, generated alerts, dedupe on second tick, reset and retrigger on later tick, and status metrics update.
  QA scenarios (name the exact tool + invocation): happy: `pytest backend/tests/test_scheduler.py backend/tests/test_monitoring_integration.py`; failure: adapter failure for one source records source error while other sources continue, evidence `.omo/evidence/task-8-stock-data-monitor-build.txt`.
  Commit: N | feat(runtime): run monitoring scheduler

- [x] 9. Add backend operational surfaces, live-smoke script, and API documentation checks
  What to do / Must NOT do: Add operational endpoints for health, scheduler state, latest prices, recent alerts, source errors, and optional live-smoke script gated by explicit env flag. Must not run live external checks by default in tests.
  Parallelization: Wave 3/4 | Blocked by: 6, 7, 8 | Blocks: 12
  References (executor has NO interview context - be exhaustive): Scope IN status/runtime in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor-build.md`; external API caveats in background research.
  Acceptance criteria (agent-executable): backend tests pass; OpenAPI JSON includes expected endpoints; live-smoke script exits with skipped status unless `RUN_LIVE_SMOKE=1` is set.
  QA scenarios (name the exact tool + invocation): happy: `pytest backend/tests/test_status_api.py`; failure: no instruments configured returns empty latest/recent alert lists without 500, evidence `.omo/evidence/task-9-stock-data-monitor-build.txt`.
  Commit: N | feat(api): expose runtime monitoring status

- [x] 10. Implement frontend instrument/rule configuration UI with mocked API TDD
  What to do / Must NOT do: Build pages/components for instrument list, create/edit form, source mapping rows for yfinance/Binance USD-M/Binance COIN-M/Hyperliquid, support/resistance/threshold fields, enable flags, validation errors, and save/delete flows. Must not expose Telegram secrets.
  Parallelization: Wave 3 | Blocked by: 3, 4 | Blocks: 11, 12
  References (executor has NO interview context - be exhaustive): C1 UI component in `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor-build.md`; API todo 4.
  Acceptance criteria (agent-executable): frontend tests pass for listing, validation, create, edit, delete, source type selection, and API error states; typecheck/build pass.
  QA scenarios (name the exact tool + invocation): happy: `npm run test -- --run` and `npm run typecheck`; failure: resistance <= support blocks submit and shows clear error, evidence `.omo/evidence/task-10-stock-data-monitor-build.txt`.
  Commit: N | feat(frontend): manage monitored instruments

- [x] 11. Implement frontend runtime dashboard and Telegram status/test UI with mocked API TDD
  What to do / Must NOT do: Build dashboard for latest prices by source, recent alerts, source errors, scheduler status, Telegram readiness, and test-send action. Must show only readiness/redacted status, never raw token/chat id.
  Parallelization: Wave 3/4 | Blocked by: 10, 5 | Blocks: 12
  References (executor has NO interview context - be exhaustive): Telegram env decision `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:33`; backend status endpoints todo 9.
  Acceptance criteria (agent-executable): frontend tests pass for dashboard loading, empty state, recent alert rendering, Telegram not configured state, successful test-send, failed test-send, and redaction.
  QA scenarios (name the exact tool + invocation): happy: `npm run test -- --run` and `npm run build`; failure: mocked Telegram readiness false disables test-send and explains env vars required, evidence `.omo/evidence/task-11-stock-data-monitor-build.txt`.
  Commit: N | feat(frontend): show monitoring dashboard

- [x] 12. Integrate Docker compose, full verification gates, and runtime smoke evidence
  What to do / Must NOT do: Add backend/frontend Dockerfiles, docker-compose with persistent data volume and env wiring, startup docs in comments/env example only, and run full backend/frontend/build/compose smoke. Must not commit real credentials or require human browser interaction.
  Parallelization: Wave 4 | Blocked by: 8, 9, 11 | Blocks: final verification
  References (executor has NO interview context - be exhaustive): User stack decision `/opt/ocode/wavemonitor/.omo/drafts/stock-data-monitor.md:30`; verification strategy in this plan.
  Acceptance criteria (agent-executable): full local commands pass: backend tests, frontend tests/typecheck/build, Docker images build, compose starts, `curl -fsS http://localhost:8000/health` returns HTTP 200 status OK, frontend HTTP root responds, backend can write the SQLite volume, missing Telegram env keeps health OK/readiness false, and compose logs show no crash loop.
  QA scenarios (name the exact tool + invocation): happy: `docker compose up --build -d`, `curl http://localhost:<backend-port>/health`, `curl http://localhost:<frontend-port>/`; failure: missing Telegram env keeps app healthy with readiness false, evidence `.omo/evidence/task-12-stock-data-monitor-build.txt`.
  Commit: N | chore(docker): package monitor runtime

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [x] F1. Plan compliance audit: read this plan and changed files; verify every Must have is implemented and every Must NOT have is respected; evidence `.omo/evidence/f1-plan-compliance-stock-data-monitor-build.md`.
- [x] F2. Code quality review: run diagnostics/type/lint/test/build checks and inspect architecture for slop, hidden floats in rule math, secret leakage, duplicate code, and oversized modules; evidence `.omo/evidence/f2-code-quality-stock-data-monitor-build.md`.
- [x] F3. Real manual QA: start Docker compose, use HTTP/API/browser-capable tooling to create an instrument with mocked/test-mode data or seeded fake adapter mode, view frontend dashboard, and verify alert path without real Telegram secret; evidence `.omo/evidence/f3-manual-qa-stock-data-monitor-build.md`.
- [x] F4. Scope fidelity: confirm no trading/account/auth/cloud/CI/websocket-first scope was added and no `.omo/` artifacts were overwritten except evidence; evidence `.omo/evidence/f4-scope-fidelity-stock-data-monitor-build.md`.

## Commit strategy
- Do not commit unless the user explicitly asks for commits.
- If commits are later requested, use small atomic commits by wave:
  - `chore(scaffold): initialize monitor project`
  - `feat(backend): add configuration and monitoring APIs`
  - `feat(adapters): fetch market prices`
  - `feat(rules): evaluate support resistance alerts`
  - `feat(frontend): add configuration console`
  - `chore(docker): package runtime`
- Before any commit: inspect `git status`, `git diff`, and recent log if a git repo has been initialized; stage only intended files and never secrets.

## Success criteria
- A fresh clone/copy of the workspace can run the app with Docker compose using `.env.example` as guidance and no real Telegram secret required for health.
- The web console can create/edit/delete a monitored instrument and configure yfinance, Binance USD-M/COIN-M, and Hyperliquid mappings.
- Backend can poll mocked or real-configured providers through adapter boundaries and persist latest observations/status.
- Long-only risk/reward, near-support, and resistance-breakout alerts are Decimal-safe, tested, and deduped.
- Telegram sends are tested with mocks, real credentials are env-only, and APIs/UI never reveal secret values.
- Backend tests, frontend tests, typecheck/builds, and Docker smoke checks pass with evidence files recorded.
