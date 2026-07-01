# Backend API contract

This file mirrors the backend MVP routes from `.omo/plans/stock-data-monitor-build.md` and the Todo 9 operational surfaces.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Returns `{ status: "ok", telegram_ready: boolean }` without requiring optional Telegram env. |
| GET | `/api/auth/session` | Returns `{ authenticated, auth_enabled }`; auth endpoints stay public so the frontend can decide whether to show the password gate. |
| POST | `/api/auth/login` | Accepts `{ password }`, compares it to `WAVEMONITOR_WEB_PASSWORD`, and issues a 7-day `HttpOnly` `wavemonitor_session` cookie when valid. |
| POST | `/api/auth/logout` | Clears the `wavemonitor_session` cookie. |
| GET | `/api/symbols/query` | Query params: `provider`, `market_type`, `q`. Returns realtime symbol options as `{ options: [{ symbol, label, provider, market_type }] }`. |
| GET | `/api/instruments` | Lists configured instruments with source mappings. |
| POST | `/api/instruments` | Creates an instrument and source mappings. |
| PUT | `/api/instruments/{instrument_id}` | Replaces instrument fields and source mappings. |
| DELETE | `/api/instruments/{instrument_id}` | Deletes an instrument and its source mappings. |
| GET | `/api/instruments/{instrument_id}/status` | Returns the instrument enabled flag, per-source latest price/error/`last_invalid_state` (rule invalid reason when price is not above support), and recent alerts for that instrument. |
| GET | `/api/prices/latest` | Returns collection-level latest successful price observations by source mapping. Empty when no instruments or prices exist. |
| GET | `/api/alerts` | Returns recent alert events. Empty when no alerts exist. |
| GET | `/api/source-errors` | Returns collection-level latest source mappings whose most recent observation is an error. Empty when no source errors exist. |
| GET | `/api/runtime` | Returns scheduler/provider/Telegram readiness, polling counters, alert/delivery counters, and last tick timestamps. |
| GET | `/api/telegram/readiness` | Returns Telegram readiness only; secrets are never exposed. |
| POST | `/api/telegram/test` | Sends a Telegram test only when credentials are configured; response/logs redact secrets. |

## Authentication

When `WAVEMONITOR_WEB_PASSWORD` is unset, `/api/*` remains public for local/development compatibility. When it is set, every `/api/*` route requires the signed `wavemonitor_session` cookie except `/api/auth/session`, `/api/auth/login`, and `/api/auth/logout`. `/health` is always public.

The cookie is signed with `WAVEMONITOR_SESSION_SECRET` when set; otherwise the backend generates a random secret on first start and persists it beside the SQLite database file (`session_secret` next to the DB path, or `/data/session_secret` in the default Docker layout).

## Live smoke guard

`backend/scripts/live_smoke.py` is optional and must be explicitly gated with `RUN_LIVE_SMOKE=1`. The default invocation skips without constructing live provider clients or making external calls.
