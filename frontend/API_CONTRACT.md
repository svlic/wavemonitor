# Frontend API contract stub

The frontend scaffold expects these backend surfaces and must tolerate failures recoverably.

```ts
type HealthResponse = {
  readonly status: "ok";
  readonly telegram_ready: boolean;
};

type RuntimeResponse = {
  readonly scheduler_ready: boolean;
  readonly providers_ready: boolean;
  readonly telegram_ready: boolean;
};
```

Todo 1 uses `GET /api/runtime` only to prove the root shell can show an API-error state. CRUD, status, alert, and Telegram test interactions are reserved for later todos.
