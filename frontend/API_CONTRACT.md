# Frontend API contract

The canonical HTTP contract is [`backend/API_CONTRACT.md`](../backend/API_CONTRACT.md).

## Frontend integration

- **Validation**: Zod schemas live in `src/api/schemas.ts`; `src/api/client.ts` parses responses and throws `ApiError` on mismatch.
- **Instrument by id**: There is no `GET /api/instruments/{id}`; `getInstrument` loads `GET /api/instruments` and selects by numeric `id`.
- **Auth**: When the backend enables `WAVEMONITOR_WEB_PASSWORD`, the UI uses `/api/auth/*` and sends cookies on API calls.

For route tables and response field definitions, use the backend contract only.