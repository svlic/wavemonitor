# F4 Scope Fidelity Audit — Stock Data Monitor Build

## Verdict

verdict: approve

## Audit constraints observed

- Working directory: `/opt/ocode/wavemonitor` verified with `pwd`.
- Read-only/product-safe audit: no product edits performed. This evidence file is the only intended write.
- No live calls: did not run Docker, provider smoke, Telegram, app servers, or external API calls.
- No commit: `git status --short` returned `fatal: not a git repository (or any of the parent directories): .git`, matching the non-git/no-commit expectation.
- Required search note: `rg` is not installed (`/bin/bash: line 1: rg: command not found`), so the audit used the Grep tool plus targeted Bash filesystem checks.

## Plan guardrails read

Read `.omo/plans/stock-data-monitor-build.md` and confirmed the Must-NOT scope at lines 36-43:

- No trading, order placement, exchange auth, portfolio tracking, or PnL accounting beyond configured risk/reward math.
- No Telegram bot token or channel/chat id stored in DB or exposed raw through APIs/UI.
- No login, roles, multi-tenant accounts, cloud deployment, or CI unless later requested.
- No unit-test dependency on real yfinance/Binance/Hyperliquid/Telegram calls.
- No float alert-rule arithmetic.
- No websocket-first MVP ingestion.
- No `.omo/` planning artifact overwrite except adding task evidence under `.omo/evidence/`.

Also read `.omo/evidence/verify-f1-blocker-fix-contract-alignment.md`, `.omo/start-work/ledger.jsonl`, and `.omo/boulder.json`.

## Forbidden scope search results

Searched source/config for forbidden scope terms including trading/order placement, exchange auth/API keys, portfolio, PnL, positions, liquidation, login/auth/roles/OAuth, charts/backtesting/indicators, websocket-first ingestion, cloud/CI, real secrets, and default live calls.

Narrowed first-party search results:

- Backend first-party Python (`backend/**/*.py`) forbidden-scope grep: no matches for trading/order/auth/portfolio/PnL/positions/liquidation/login/OAuth/roles/backtesting/indicators/charts/websocket/cloud/CI/exchange-key surfaces.
- Frontend source TS (`frontend/src/**/*.ts`) forbidden-scope grep: no matches.
- Frontend source TSX (`frontend/src/**/*.tsx`) matches only ARIA/status text in `Dashboard.tsx` and `InstrumentForm.tsx` (`role="alert"`, `role="status"`), not trading/auth/chart/portfolio features.
- Broad search noise existed in dependency/build artifacts (`.venv`, `node_modules`, `frontend/dist`) and in `.omo` plan/draft/evidence text that states guardrails. Those are not product-scope implementations.
- CI/cloud checks: `test -d .github` returned `1`; `test -f .gitlab-ci.yml` returned `1`. No GitHub Actions/GitLab CI artifact found at those checked paths.

## Provider and live-call fidelity

Provider code read: `backend/src/wavemonitor_backend/adapters.py`.

Findings:

- `YFinanceAdapter` is market-data only: constructs a `yf.Ticker(symbol)` lazily through `_default_ticker_factory`, reads `fast_info.last_price`, then falls back to `history(period="1d", interval="1m")`. No credential input, account API, order API, or trading method exists.
- `BinanceFuturesAdapter` is market-data only: routes by `MarketType.USD_M_FUTURES` / `MarketType.COIN_M_FUTURES` to injected clients and calls only `mark_price(symbol)` then `ticker_price(symbol)`. No API key/secret, account, balance, position, margin, leverage, or order method exists.
- `HyperliquidAdapter` is market-data only: uses injected `info_client.all_mids().get(symbol)`. No wallet/private key/auth/order/account surface exists.
- `backend/src/wavemonitor_backend/monitoring.py` uses `SourcePoller.poll()` and `MonitoringScheduler.run_tick()` to poll enabled source mappings, record observations/errors, evaluate long-only alert rules, and optionally send Telegram alerts. No websocket service or subscription loop is present.
- `backend/scripts/live_smoke.py` is default-safe: without `RUN_LIVE_SMOKE=1`, it prints `SKIPPED live smoke: set RUN_LIVE_SMOKE=1 to call live providers.` and exits 0. Even with the flag, it only prints that live checks are not implemented. No default live provider call path exists.

## Credential and secret exposure audit

Files read/searched:

- `backend/src/wavemonitor_backend/settings.py`
- `backend/src/wavemonitor_backend/notifier.py`
- `backend/src/wavemonitor_backend/models.py`
- `backend/src/wavemonitor_backend/app.py`
- `frontend/src/api/client.ts`
- `frontend/src/pages/dashboard/Dashboard.tsx`
- `frontend/src/pages/instruments/InstrumentForm.tsx`
- `docker-compose.yml`
- `.env.example`
- `frontend/docker/nginx.conf`

Findings:

- Exchange credential surfaces: first-party source/config search found no `BINANCE_*KEY`, `HYPERLIQUID_*KEY`, `YFINANCE_*KEY`, `API_KEY`, or exchange secret settings in backend/frontend source. Provider adapters use injected unauthenticated market-data clients only.
- Telegram env names exist only where expected:
  - `settings.py` defines `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, reads them from env into runtime-only settings, and exposes only `telegram_ready` via `public_status()`.
  - `notifier.py` uses the runtime token/chat id only when `settings.telegram_ready` is true, sends via Telegram Bot API, and returns `None` when missing.
  - `Dashboard.tsx` displays an instruction to set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, but does not read or expose their values.
- DB schema in `models.py` contains `TelegramDelivery` with `chat_ref="redacted"`, `telegram_message_id`, and `safe_error`; no Telegram token or raw chat id columns exist.
- API responses in `app.py` expose `telegram_ready` and redacted delivery status only; no raw Telegram token/chat id field is in the response models.
- `docker-compose.yml` passes `TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}` and `TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID:-}` only to the backend service, with empty defaults. The frontend service receives no Telegram or exchange credential env vars.
- `.env.example` contains blank placeholders only and states not to commit real values. `test -f .env` returned `1`, so no local `.env` file was present during this audit.
- `frontend/docker/nginx.conf` only proxies `/health` and `/api/` to backend and serves static files; no secrets are embedded.
- Broad secret-pattern search found test fixtures such as `123456:secret-token` under backend tests and dependency noise, but no real secret file or first-party config containing live credentials was identified.

## Frontend/compose/env scope fidelity

- `frontend/src/api/client.ts` contains API client methods for runtime, latest prices, recent alerts, source errors, Telegram test, and instrument CRUD only. No trading, order, portfolio, login/auth, charting/backtesting, or exchange-credential API methods exist.
- `frontend/src/pages/instruments/InstrumentForm.tsx` renders only instrument/rule/source mapping fields: provider, market type, symbol, support/resistance, thresholds, enabled flags. No exchange credentials, order forms, positions, portfolio, PnL, liquidation, or login surfaces.
- `frontend/src/pages/dashboard/Dashboard.tsx` renders runtime readiness, latest prices, recent alerts, source errors, and Telegram readiness/test. It exposes readiness only, not raw Telegram credentials.
- `docker-compose.yml` defines only backend, frontend, and a SQLite named volume. No cloud/CI/deployment service, secret store, or frontend credential injection exists.

## `.omo/` preservation check

- `.omo/plans/stock-data-monitor-build.md` was read and remains the active plan content inspected for Must-NOT lines and final F4 requirement.
- `.omo/start-work/ledger.jsonl` was read and contains 12 task-completed entries for tasks 1-12; no new ledger entry was written during this F4 audit.
- `.omo/boulder.json` was read and still points to active work id `stock-data-monitor-build` and active plan `.omo/plans/stock-data-monitor-build.md`.
- `.omo/evidence/verify-f1-blocker-fix-contract-alignment.md` was read and reports no unauthorized backend/Docker/plan/ledger/Boulder edits by the blocker-fix worker.
- Pre-write check `test -e .omo/evidence/f4-scope-fidelity-stock-data-monitor-build.md` returned `1`, so this F4 evidence file did not exist before this audit. Adding it is allowed evidence under the plan.
- Workspace is non-git, so no commit/status diff is available or expected.

## Conclusion

The inspected current source/config remains within the planned market-data monitoring scope after the contract fix. Providers are market-data only, there are no exchange credential/auth/account surfaces, frontend/compose/env do not expose Telegram token/chat id or exchange API keys, default live calls are gated/skipped, no cloud/CI scope was added, and `.omo/` preservation is consistent with evidence-only additions.

verdict: approve
