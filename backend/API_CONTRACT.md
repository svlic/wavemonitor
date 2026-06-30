# Backend API contract

This file mirrors the backend MVP routes from `.omo/plans/stock-data-monitor-build.md` and the Todo 9 operational surfaces.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Returns `{ status: "ok", telegram_ready: boolean }` without requiring optional Telegram env. |
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

## Live smoke guard

`backend/scripts/live_smoke.py` is optional and must be explicitly gated with `RUN_LIVE_SMOKE=1`. The default invocation skips without constructing live provider clients or making external calls.
