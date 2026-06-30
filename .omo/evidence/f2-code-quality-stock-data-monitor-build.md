# F2 Code Quality/Security/Slop Verification: Typed-Mock Cleanup

## Verdict

verdict: approve

## Scope and constraints

Read-only verification pass after the typed-mock cleanup. Product code, tests, plan, ledger, and Boulder were not modified. No Docker services were started; only `docker compose config` was run. No live external APIs, Telegram sends, yfinance/Binance/Hyperliquid live calls, or commits were performed. The only write from this verifier was overwriting this evidence file.

Working directory: `/opt/ocode/wavemonitor`

## Required evidence read

Read `.omo/evidence/f2-blocker-fix-typed-mocks.txt`.

The cleanup worker claimed the previous F2 blocker was fixed by replacing three frontend test-only `as any` casts with typed `InstrumentWithMappings` mocks:

- `frontend/src/tests/Instruments.test.tsx`: import `type { InstrumentWithMappings }`; define `mockInstruments: readonly InstrumentWithMappings[]`; pass it directly to `mockResolvedValue`.
- `frontend/tests/Dashboard.test.tsx`: import `type { InstrumentWithMappings }`; use `satisfies readonly InstrumentWithMappings[]` for the inline `getInstruments` mock.

## Previous blocker resolution

Read and inspected:

- `frontend/src/tests/Instruments.test.tsx`
- `frontend/tests/Dashboard.test.tsx`
- `frontend/src/api/client.ts`

Findings:

- `frontend/src/tests/Instruments.test.tsx` imports `InstrumentWithMappings` from `../api/client` and defines `const mockInstruments: readonly InstrumentWithMappings[] = [...]`.
- `frontend/src/tests/Instruments.test.tsx` now calls `vi.mocked(apiClient.getInstruments).mockResolvedValue(mockInstruments)` without `as any`.
- `frontend/tests/Dashboard.test.tsx` imports `InstrumentWithMappings` from `../src/api/client` and uses `] satisfies readonly InstrumentWithMappings[]` for the inline mocked instrument array.
- `frontend/src/api/client.ts` defines `InstrumentWithMappingsSchema = InstrumentSchema.extend({ source_mappings: z.array(SourceMappingSchema) })` and `export type InstrumentWithMappings = z.infer<typeof InstrumentWithMappingsSchema>`.
- Direct scans of `frontend/src` and `frontend/tests` found no `as any`, `@ts-ignore`, `@ts-expect-error`, or common non-null assertion patterns.

Conclusion: the previous blocker is resolved. The three cited casts are gone and the touched tests use typed `InstrumentWithMappings` mocks.

## Required command results

### Backend tests

Command, from repo root:

```bash
.venv/bin/pytest backend/tests -vv
```

Result: pass.

Evidence summary: `67 passed, 1 warning in 9.60s`. The warning is a Starlette/FastAPI TestClient deprecation notice about `httpx`; it is not a test failure.

### Frontend tests

Command, from `frontend`:

```bash
npm test -- --run
```

Result: pass.

Evidence summary: `Test Files 5 passed (5)`, `Tests 27 passed (27)`.

### Frontend typecheck

Command, from `frontend`:

```bash
npm run typecheck
```

Result: pass.

Evidence summary: `tsc --noEmit` exited 0.

### Frontend production build

Command, from `frontend`:

```bash
npm run build
```

Result: pass.

Evidence summary: `tsc --noEmit && vite build` exited 0; Vite built successfully:

- `dist/index.html`
- `dist/assets/index-CCJ0xsfj.css`
- `dist/assets/index-QzA65NQr.js`

### Docker Compose config render

Command, from repo root:

```bash
docker compose config
```

Result: pass.

Evidence summary: compose rendered backend/frontend services, SQLite volume, backend healthcheck, and frontend `depends_on` without starting services. Telegram environment defaults render empty:

```yaml
TELEGRAM_BOT_TOKEN: ""
TELEGRAM_CHAT_ID: ""
```

## Slop/security scans

### TypeScript escape hatches and non-null assertions

Searched first-party frontend source/tests:

- `frontend/src`
- `frontend/tests`

Patterns searched included:

- `as any`
- `@ts-ignore`
- `@ts-expect-error`
- common non-null assertion shapes such as `x!.`, `x![`, `x!)`, `x!;`, `x!,`

Result: no matches in first-party frontend source/tests.

A final repo scanner excluding `.venv`, `node_modules`, `dist`, build artifacts, `.git`, `.pytest_cache`, and `__pycache__` found `as any` / TypeScript directive strings only in evidence documents, not product source or tests.

### Hardcoded Telegram secrets and exchange API keys

Searched first-party source/tests for Telegram/env/API-key indicators including Telegram token/chat id names, `api_key`, `apikey`, Binance/Hyperliquid/YFinance key strings, and provider/live-call terms.

Findings:

- Runtime Telegram credentials are read only from environment in `backend/src/wavemonitor_backend/settings.py` via `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- `Settings.public_status()` exposes only `telegram_ready`.
- `docker compose config` uses empty Telegram defaults, not real secrets.
- Test fixtures include fake Telegram values such as `123456:secret-token` and `-100987654321`; these are used in redaction tests, not production defaults.
- No hardcoded Binance, Hyperliquid, yfinance, or other exchange API key was found in first-party source/tests.

Result: no secret/key leakage blocker.

### Hidden live default calls

Inspected live-call surfaces and relevant tests:

- `backend/src/wavemonitor_backend/adapters.py`
- `backend/src/wavemonitor_backend/notifier.py`
- `backend/src/wavemonitor_backend/app.py`
- `backend/tests/test_adapters.py`
- `backend/tests/test_status_api.py`

Findings:

- Required audit commands did not invoke live providers or Telegram.
- Adapter tests inject fake clients/factories; `test_adapters.py` includes `_fail_network_call` to catch unexpected yfinance network construction in mocked tests.
- Live smoke behavior is gated; `test_live_smoke_script_skips_without_explicit_gate` verifies the live smoke script skips unless `RUN_LIVE_SMOKE=1` is set.
- Telegram send path requires configured env credentials and tests use mocked transport/responses.

Result: no hidden default live-call blocker.

### Float arithmetic in rule engine

Read and inspected:

- `backend/src/wavemonitor_backend/rules.py`
- `backend/src/wavemonitor_backend/schemas.py`

Findings:

- Rule inputs are typed as `Decimal`.
- `rules.py` imports `Decimal` and performs rule math with Decimal values:
  - `near_support_metric = (price - support) / price`
  - `risk_reward_ratio(...): return (resistance - price) / denominator`
- `schemas.py` parses accepted decimal values into `Decimal` and rejects floats for decimal-string inputs by raising `ValueError("Decimal values must be provided as strings, Decimal, or integers")`.
- Backend tests passed, including explicit rule/model coverage for Decimal exactness and float rejection.

Result: no hidden float arithmetic blocker in the rule engine.

### Broad exception conversions

Searched backend source for broad exception handling and inspected matches.

Findings:

- `backend/src/wavemonitor_backend/adapters.py` has `except Exception as exc` at provider boundaries for yfinance, Binance, and Hyperliquid adapter calls.
- These exceptions are not swallowed; they are converted to typed `AdapterError` values with source, market type, symbol, kind, message, and metadata.
- `_error_kind_from_exception` classifies rate limit, timeout, and provider-error cases.
- `MalformedProviderPriceError` is converted to `AdapterErrorKind.MALFORMED_PRICE`.
- Backend adapter tests passed for timeout, rate-limit, malformed price, missing symbol, and provider error paths.
- `backend/src/wavemonitor_backend/notifier.py` catches specific `HTTPError` and `URLError`, returning typed `TelegramHttpFailure`; these are boundary conversions, not swallowed errors.

Result: broad catches are typed provider-error boundary conversions, not a blocker.

## Pure LOC check

Representative touched/large files were checked by counting non-blank, non-comment lines:

```text
frontend/src/tests/Instruments.test.tsx: 140 pure LOC
frontend/tests/Dashboard.test.tsx: 164 pure LOC
frontend/src/api/client.ts: 206 pure LOC
backend/src/wavemonitor_backend/rules.py: 212 pure LOC
backend/src/wavemonitor_backend/adapters.py: 186 pure LOC
backend/src/wavemonitor_backend/app.py: 242 pure LOC
backend/tests/test_adapters.py: 199 pure LOC
backend/tests/test_telegram.py: 229 pure LOC
```

Findings:

- No representative touched/large file is over 250 pure LOC.
- `backend/src/wavemonitor_backend/app.py` is in the warning band at 242 pure LOC, but not over the >250 defect threshold.

Result: no file-size blocker.

## Final decision

verdict: approve

Rationale: the sole prior F2 blocker is resolved; no `as any` remains in first-party frontend source/tests; the two touched test files use typed `InstrumentWithMappings` mocks; all required backend/frontend/build/config commands passed; source/test scans found no TypeScript escape hatches, hardcoded real secrets/API keys, hidden live-call defaults, float rule-engine arithmetic, swallowed broad exceptions, or >250 pure-LOC representative files.
