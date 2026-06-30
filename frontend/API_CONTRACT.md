# Frontend API contract

Zod schemas in `src/api/client.ts` mirror [`backend/API_CONTRACT.md`](../backend/API_CONTRACT.md). There is no `GET /api/instruments/{id}`; `getInstrument` loads `GET /api/instruments` and selects by numeric `id`.

## Routes used by the UI

| Method | Path | Client method |
| --- | --- | --- |
| GET | `/api/runtime` | `getRuntime` |
| GET | `/api/prices/latest` | `getLatestPrices` |
| GET | `/api/alerts` | `getRecentAlerts` |
| GET | `/api/source-errors` | `getSourceErrors` |
| GET | `/api/instruments` | `getInstruments`, `getInstrument` |
| POST | `/api/instruments` | `createInstrument` |
| PUT | `/api/instruments/{instrument_id}` | `updateInstrument` |
| DELETE | `/api/instruments/{instrument_id}` | `deleteInstrument` |
| POST | `/api/telegram/test` | `testTelegram` |

## Response shapes (summary)

- **RuntimeResponse**: `scheduler_ready`, `providers_ready`, `telegram_ready`, tick counters (`enabled_sources`, `polled_sources`, `observations_written`, `source_errors`, `alert_events_created`, `telegram_deliveries_attempted`), `last_tick_started_at` / `last_tick_finished_at` (nullable ISO strings).
- **LatestPrice**: `instrument_id`, `instrument_name`, `source_mapping_id`, `provider`, `market_type`, `symbol`, `last_price`, `last_observed_at`, `last_error` (nullable).
- **RecentAlert**: `id`, `instrument_id`, `source_mapping_id`, `alert_kind`, `price`, `message`, `triggered_at`.
- **SourceError**: `instrument_id`, `instrument_name`, `source_mapping_id`, `provider`, `market_type`, `symbol`, `last_observed_at`, `last_error`.
- **InstrumentWithMappings**: numeric `id`; `source_mappings[]` with `id`, `provider`, `market_type`, `symbol`, `enabled` (no per-mapping `instrument_id` in API).

Invalid JSON or schema mismatch surfaces as `ApiError` so pages can show recoverable error states.