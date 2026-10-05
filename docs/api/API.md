# ECHO — API Reference

Interactive OpenAPI documentation is generated from the code: **http://localhost:8080/api/swagger-ui**
(raw spec: `/api/docs`). The ML service's own docs are at `http://ml-service:8000/docs` inside the Docker
network (or `http://localhost:8000/docs` when run locally).

Errors are `application/problem+json` (RFC 7807) with a stable `type`, e.g.
`https://echo.dev/problems/plan-limit` (403), `rate-limited` (429), `validation` (400, with `errors{field}`),
`ml-service-unavailable` (503).

Authentication: `Authorization: Bearer <JWT>` from `/api/auth/login`, or `X-API-Key: echo_...` (Pro/Enterprise).

## Public backend API (`/api`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | — | Create a Free account → `{token, expiresAt, user}` |
| POST | `/auth/login` | — | Email + password → JWT |
| GET | `/auth/me` | user | User, plan limits, today's usage, unread alerts |
| GET | `/companies/search?q=` | — | Resolve name / ticker / former name to SEC filers (fuzzy) |
| GET | `/companies/{id}` | — | Company profile |
| GET | `/companies/{id}/report[?asOf=YYYY-MM-DD]` | — | **200** `{status:READY, report}` or **202** `{status:PENDING, job, report?}` (stale report while refreshing) |
| POST | `/companies/{id}/analyze` | user | Force a fresh analysis (plan quota) → 202 job |
| GET | `/jobs/{id}` | — | Job status (`QUEUED/RUNNING/DONE/FAILED`), `reportId` when done |
| GET | `/reports/{id}` | — | A stored report by id |
| GET | `/reports/{id}/export?format=csv\|pdf` | user | CSV (all plans) / PDF executive report (Pro+) |
| GET | `/companies/{id}/history?from=&to=` | — | Score history: `LIVE` reports + point-in-time `BACKFILL` points (Free: 12 months) |
| GET | `/compare?ids=1,2,3` | — | Latest pillar scores side by side (Free 2, Pro 4, Enterprise 8) |
| GET/POST | `/watchlists` | user | List (a default list is created) / create |
| DELETE | `/watchlists/{id}` | user | Delete a watchlist |
| POST | `/watchlists/{id}/items` | user | `{companyId, scoreDropThreshold}` add or update |
| DELETE | `/watchlists/{id}/items/{companyId}` | user | Remove |
| GET | `/alerts` | user | Alert inbox (`SCORE_DROP`, `NEW_SIGNAL`) |
| PATCH | `/alerts/{id}/read`, POST `/alerts/read-all` | user | Mark read |
| GET | `/billing/plans` | — | Plan catalogue |
| POST | `/billing/checkout` | user | `{plan}` change plan (demo billing) |
| GET/POST | `/me/api-keys` | user | List / create (secret shown once) |
| DELETE | `/me/api-keys/{id}` | user | Revoke |
| GET | `/universe` | — | Demo companies + case-study dates |
| GET | `/models` | — | Model cards (metrics vs baseline, gate decision, data, limitations) |
| GET | `/stats` | — | Landing-page counters |
| POST | `/sentiment` | user | `{texts:[...]}` score headlines with the champion NLP model |
| GET | `/admin/users`, PATCH `/admin/users/{id}` | admin | Users, change plan/role |
| GET | `/admin/jobs` | admin | Recent analysis jobs |
| GET / POST | `/admin/monitoring`, `/admin/monitoring/run` | admin | Drift (PSI) / freshness report |
| GET / POST | `/admin/retrain` | admin | Retraining jobs / start one `{model, promote}` |
| GET | `/admin/ml-health` | admin | ML service health and loaded model versions |

Actuator (internal management port 8081, not published by Docker Compose): `/actuator/health` (liveness/readiness
probes), `/actuator/info`, `/actuator/metrics`, `/actuator/prometheus`.

`GET /api/radar` (public): the latest stored report for every demo-universe (company, as-of) pair, with health
score, band, distress probability and signal count, plus the pairs not analysed yet. Read-only: it never starts an analysis.

## Internal ML-service API (`ml-service:8000`, not exposed by Docker Compose)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Status, demo mode, explanation provider, loaded model cards |
| POST | `/v1/resolve` | `{query, market, limit}` → candidates `[{market, market_id, name, ticker, former_names, match_score, is_demo}]` |
| POST | `/v1/analyze` | `{company:{market, market_id}, as_of?, include_backfill}` → `AnalysisResult` (schema `app/schemas/analysis.py`) |
| POST | `/v1/sentiment` | `{texts}` → label, polarity, class probabilities |
| GET | `/v1/universe` | Demo universe |
| GET | `/v1/models` | All model cards (champions and challengers) |
| GET / POST | `/v1/monitoring`, `/v1/monitoring/run` | Latest / new drift report |
| GET / POST | `/v1/admin/retrain` | Header `X-Admin-Token`; start or list retraining subprocesses |

## `AnalysisResult` highlights

- `health {score, band, confidence, raw_score, override}` — score is `null` below 40 % coverage.
- `pillars[].factors[]` — `kind` (ML/Stat/Rule), `value`, `peer_percentile`, `score`, `weight`,
  **`impact`** (exact points; `50 + Σ impact = raw_score`), `evidence` ids.
- `distress {probability_12m, risk_band, drivers[] (SHAP, log-odds)}`, `segment`, `anomalies[]`, `forecasts[]` (p10/p50/p90).
- `signals[]`, `events[]`, `news`, `employee`, `timeseries`, `history[]` (point-in-time backfill).
- `evidence{id → {type, title, url, date, source}}`, `sources[]` (provenance per source), `models{name → version}`.
- `summary {text, pillar_notes, key_risks, generator, grounding_check}`, `disclaimer`.
