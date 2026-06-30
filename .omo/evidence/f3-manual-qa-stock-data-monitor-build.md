# F3 manual QA: stock data monitor build

Date: Tue Jun 30 2026
Workspace: `/opt/ocode/wavemonitor`
Verdict: approve

## Constraints observed

- Used Docker/manual QA only.
- No product files were edited.
- No live providers were enabled; `RUN_LIVE_SMOKE=1` was not used.
- No Telegram secrets were provided.
- Cleanup was run with `docker compose down -v` and verified.

## 1. Workspace and compose inspection

Command:

```bash
pwd && ls
```

Result:

```text
/opt/ocode/wavemonitor
backend
DESIGN.md
docker
docker-compose.yml
frontend
pyproject.toml
```

Relevant compose facts from `docker-compose.yml`:

```yaml
services:
  backend:
    environment:
      DATABASE_URL: sqlite:////data/wavemonitor.sqlite3
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}
      TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID:-}
    ports:
      - "8000:8000"
    volumes:
      - wavemonitor-sqlite:/data
  frontend:
    depends_on:
      backend:
        condition: service_healthy
    ports:
      - "5173:8080"
volumes:
  wavemonitor-sqlite:
```

Backend contract confirms required surfaces:

```text
GET /health -> { status: "ok", telegram_ready: boolean }
GET /api/instruments
POST /api/instruments
GET /api/instruments/{instrument_id}/status
GET /api/prices/latest
GET /api/alerts
GET /api/source-errors
GET /api/runtime
GET /api/telegram/readiness
```

Canonical backend schema confirmed from `backend/src/wavemonitor_backend/schemas.py` and `models.py`:

- `InstrumentRequest`: `name`, `enabled`, `support`, `resistance`, `near_support_threshold`, `risk_reward_threshold`, `source_mappings`.
- `SourceMappingRequest`: `provider`, `market_type`, `symbol`, `enabled`.
- Allowed provider enum values: `yfinance`, `binance`, `hyperliquid`.
- Allowed market type enum values: `equity`, `usd_m_futures`, `coin_m_futures`, `perpetual`.

## 2. Build and start current stack

Command:

```bash
docker compose up --build -d
```

Result excerpt:

```text
Image wavemonitor-frontend Building
Image wavemonitor-backend Building
...
#24 [frontend build 6/6] RUN npm run build
#24 0.463 > wavemonitor-frontend@0.1.0 build
#24 0.463 > tsc --noEmit && vite build
#24 5.470 vite v8.1.0 building client environment for production...
#24 5.741 dist/index.html                   0.40 kB │ gzip:  0.27 kB
#24 5.741 dist/assets/index-CCJ0xsfj.css    5.23 kB │ gzip:  1.51 kB
#24 5.741 dist/assets/index-QzA65NQr.js   273.63 kB │ gzip: 82.20 kB
#24 5.742 ✓ built in 270ms
...
Network wavemonitor_default Created
Volume wavemonitor_wavemonitor-sqlite Created
Container wavemonitor-backend-1 Started
Container wavemonitor-backend-1 Healthy
Container wavemonitor-frontend-1 Started
```

## 3. Backend health and frontend-origin runtime proxy

Command:

```bash
python - <<'PY'
import json
import urllib.request

def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        body = response.read().decode()
        print(f"GET {url} -> {response.status} {response.getheader('content-type')}")
        print(body[:2000])

get('http://127.0.0.1:8000/health')
get('http://127.0.0.1:5173/api/runtime')
PY
```

Result:

```text
GET http://127.0.0.1:8000/health -> 200 application/json
{"status":"ok","telegram_ready":false}
GET http://127.0.0.1:5173/api/runtime -> 200 application/json
{"scheduler_ready":false,"providers_ready":false,"telegram_ready":false,"enabled_sources":0,"polled_sources":0,"observations_written":0,"source_errors":0,"alert_events_created":0,"telegram_deliveries_attempted":0,"last_tick_started_at":null,"last_tick_finished_at":null}
```

Assessment:

- Backend `/health` is OK.
- Missing Telegram env keeps health OK and readiness false.
- Frontend-origin `/api/runtime` proxy works.
- Runtime response exposes readiness/counters only; no Telegram secrets are exposed.

## 4. Frontend HTML/app shell probe

Command:

```bash
python - <<'PY'
import urllib.request
for url in ('http://127.0.0.1:5173/', 'http://127.0.0.1:5173/assets/index-QzA65NQr.js'):
    with urllib.request.urlopen(url, timeout=10) as response:
        body = response.read().decode(errors='replace')
        print(f"GET {url} -> {response.status} {response.getheader('content-type')} bytes={len(body)}")
        print(body[:1200])
PY
```

Result:

```text
GET http://127.0.0.1:5173/ -> 200 text/html bytes=403
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Stock Data Monitor</title>
    <script type="module" crossorigin src="/assets/index-QzA65NQr.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-CCJ0xsfj.css">
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>

GET http://127.0.0.1:5173/assets/index-QzA65NQr.js -> 200 application/javascript bytes=273630
var e=Object.create,t=Object.defineProperty,n=Object.getOwnPropertyDescriptor,r=Object.getOwnPropertyNames,...
```

Assessment: frontend production app shell is served, including root mount, title `Stock Data Monitor`, JS bundle, and CSS bundle. This is sufficient non-browser confirmation that the config/dashboard UI app is being served.

## 5. Instrument create/list/status through frontend-origin proxy

Initial negative probe used non-enum labels and confirmed the proxy/backend validation path returned 422:

```text
POST /api/instruments via frontend-origin with provider yahoo / alpha_vantage and market_type stock -> HTTP 422 Unprocessable Entity
```

Retried with canonical backend enum values and fixed frontend contract schema.

Command:

```bash
python - <<'PY'
import json
import urllib.error
import urllib.request
payload = {
    "name": "F3 Contract Fixture",
    "enabled": True,
    "support": "100.00",
    "resistance": "125.00",
    "near_support_threshold": "0.05",
    "risk_reward_threshold": "2.00",
    "source_mappings": [
        {"provider": "yfinance", "market_type": "equity", "symbol": "msft", "enabled": True},
        {"provider": "binance", "market_type": "usd_m_futures", "symbol": "btcusdt", "enabled": False},
    ],
}
request = urllib.request.Request(
    "http://127.0.0.1:5173/api/instruments",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        created = json.loads(response.read().decode())
        print(f"POST /api/instruments via frontend-origin -> {response.status}")
        print(json.dumps(created, indent=2, sort_keys=True))
except urllib.error.HTTPError as exc:
    print(f"POST failed -> {exc.code}")
    print(exc.read().decode())
    raise
instrument_id = created["id"]
for path in ("/api/instruments", f"/api/instruments/{instrument_id}/status", "/api/prices/latest", "/api/alerts", "/api/source-errors", "/api/telegram/readiness"):
    with urllib.request.urlopen(f"http://127.0.0.1:5173{path}", timeout=10) as response:
        body = json.loads(response.read().decode())
        print(f"GET {path} via frontend-origin -> {response.status}")
        print(json.dumps(body, indent=2, sort_keys=True))
PY
```

Result:

```text
POST /api/instruments via frontend-origin -> 201
{
  "enabled": true,
  "id": 1,
  "name": "F3 Contract Fixture",
  "near_support_threshold": "0.0500000000",
  "resistance": "125.0000000000",
  "risk_reward_threshold": "2.0000000000",
  "source_mappings": [
    {
      "enabled": true,
      "id": 1,
      "market_type": "equity",
      "provider": "yfinance",
      "symbol": "MSFT"
    },
    {
      "enabled": false,
      "id": 2,
      "market_type": "usd_m_futures",
      "provider": "binance",
      "symbol": "BTCUSDT"
    }
  ],
  "support": "100.0000000000"
}
GET /api/instruments via frontend-origin -> 200
[
  {
    "enabled": true,
    "id": 1,
    "name": "F3 Contract Fixture",
    "near_support_threshold": "0.0500000000",
    "resistance": "125.0000000000",
    "risk_reward_threshold": "2.0000000000",
    "source_mappings": [
      {
        "enabled": true,
        "id": 1,
        "market_type": "equity",
        "provider": "yfinance",
        "symbol": "MSFT"
      },
      {
        "enabled": false,
        "id": 2,
        "market_type": "usd_m_futures",
        "provider": "binance",
        "symbol": "BTCUSDT"
      }
    ],
    "support": "100.0000000000"
  }
]
GET /api/instruments/1/status via frontend-origin -> 200
{
  "enabled": true,
  "instrument_id": 1,
  "recent_alerts": [],
  "sources": [
    {
      "enabled": true,
      "id": 1,
      "last_error": null,
      "last_observed_at": null,
      "last_price": null,
      "market_type": "equity",
      "provider": "yfinance",
      "symbol": "MSFT"
    },
    {
      "enabled": false,
      "id": 2,
      "last_error": null,
      "last_observed_at": null,
      "last_price": null,
      "market_type": "usd_m_futures",
      "provider": "binance",
      "symbol": "BTCUSDT"
    }
  ]
}
GET /api/prices/latest via frontend-origin -> 200
[]
GET /api/alerts via frontend-origin -> 200
[]
GET /api/source-errors via frontend-origin -> 200
[]
GET /api/telegram/readiness via frontend-origin -> 200
{
  "telegram_ready": false
}
```

Assessment:

- Frontend-origin API proxy can create an instrument using the backend canonical schema matching the fixed frontend contract.
- List surface returns the created instrument and normalized symbols.
- Status surface returns enabled flag, source mappings, no latest prices/errors, and no alerts, as expected without live providers.
- Telegram readiness remains false without secrets.
- No secrets are returned by any probed API response.

## 6. SQLite container file exists and is nonzero

Command:

```bash
docker compose exec -T backend python - <<'PY'
from pathlib import Path
path = Path('/data/wavemonitor.sqlite3')
print(f"exists={path.exists()} size={path.stat().st_size if path.exists() else 0} path={path}")
PY
```

Result:

```text
exists=True size=98304 path=/data/wavemonitor.sqlite3
```

Assessment: SQLite file exists in the backend container data mount and is nonzero after creating the instrument.

## 7. Compose ps/logs: no crash loop

Command:

```bash
docker compose ps
```

Result:

```text
NAME                     IMAGE                  COMMAND                  SERVICE    CREATED          STATUS                    PORTS
wavemonitor-backend-1    wavemonitor-backend    "uvicorn wavemonitor…"   backend    59 seconds ago   Up 58 seconds (healthy)   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
wavemonitor-frontend-1   wavemonitor-frontend   "/docker-entrypoint.…"   frontend   59 seconds ago   Up 48 seconds             80/tcp, 0.0.0.0:5173->8080/tcp, [::]:5173->8080/tcp
```

Command:

```bash
docker compose logs --no-color
```

Result excerpt:

```text
frontend-1  | Configuration complete; ready for start up
frontend-1  | 2026/06/30 10:27:50 [notice] 1#1: nginx/1.29.8
frontend-1  | 172.28.0.1 - - [30/Jun/2026:10:27:56 +0000] "GET /api/runtime HTTP/1.1" 200 270 "-" "Python-urllib/3.11" "-"
frontend-1  | 172.28.0.1 - - [30/Jun/2026:10:28:01 +0000] "GET / HTTP/1.1" 200 403 "-" "Python-urllib/3.11" "-"
frontend-1  | 172.28.0.1 - - [30/Jun/2026:10:28:29 +0000] "POST /api/instruments HTTP/1.1" 201 388 "-" "Python-urllib/3.11" "-"
frontend-1  | 172.28.0.1 - - [30/Jun/2026:10:28:29 +0000] "GET /api/instruments HTTP/1.1" 200 390 "-" "Python-urllib/3.11" "-"
frontend-1  | 172.28.0.1 - - [30/Jun/2026:10:28:29 +0000] "GET /api/instruments/1/status HTTP/1.1" 200 365 "-" "Python-urllib/3.11" "-"
backend-1   | INFO:     Started server process [1]
backend-1   | INFO:     Waiting for application startup.
backend-1   | INFO:     Application startup complete.
backend-1   | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
backend-1   | INFO:     127.0.0.1:37582 - "GET /health HTTP/1.1" 200 OK
backend-1   | INFO:     172.28.0.3:53930 - "POST /api/instruments HTTP/1.1" 201 Created
backend-1   | INFO:     172.28.0.3:53946 - "GET /api/instruments HTTP/1.1" 200 OK
backend-1   | INFO:     172.28.0.3:53954 - "GET /api/instruments/1/status HTTP/1.1" 200 OK
backend-1   | INFO:     172.28.0.3:53984 - "GET /api/telegram/readiness HTTP/1.1" 200 OK
```

Assessment:

- Backend is healthy.
- Frontend is up.
- Logs show normal startup and expected probe traffic.
- No crash loop observed.
- No Telegram token/chat secret values appear in logs.

## 8. Cleanup and receipts

Command:

```bash
docker compose down -v
```

Result:

```text
Container wavemonitor-frontend-1 Stopping
Container wavemonitor-frontend-1 Stopped
Container wavemonitor-frontend-1 Removing
Container wavemonitor-frontend-1 Removed
Container wavemonitor-backend-1 Stopping
Container wavemonitor-backend-1 Stopped
Container wavemonitor-backend-1 Removing
Container wavemonitor-backend-1 Removed
Volume wavemonitor_wavemonitor-sqlite Removing
Network wavemonitor_default Removing
Volume wavemonitor_wavemonitor-sqlite Removed
Network wavemonitor_default Removed
```

Command:

```bash
python - <<'PY'
import subprocess
checks = {
    'containers': ['docker', 'ps', '-a', '--filter', 'name=wavemonitor', '--format', '{{.Names}}'],
    'volumes': ['docker', 'volume', 'ls', '--filter', 'name=wavemonitor', '--format', '{{.Name}}'],
    'networks': ['docker', 'network', 'ls', '--filter', 'name=wavemonitor', '--format', '{{.Name}}'],
}
for label, command in checks.items():
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    value = result.stdout.strip()
    print(f"{label}: {value if value else '<none>'}")
PY
```

Result:

```text
containers: <none>
volumes: <none>
networks: <none>
```

## Final verdict

verdict: approve
