# ECHO — Development Roadmap

Status (2026-10-05): **Phases 0–8 implemented; Phase 9 evaluation written up** in `docs/report/REPORT.md`.
Each phase ended with an exit check; the outcome is noted per phase below.

| Phase | Status | Exit check result |
|---|---|---|
| 0 Foundations | ✅ | Services build; 18 pytest + 4 JUnit (Testcontainers) + 4 Vitest pass; Docker Compose stack |
| 1 SEC data | ✅ | Apple FY2025 revenue 416.16B / FY2024 net income 93.74B match the 10-K; leakage unit test passes |
| 2 Scoring + contract | ✅ | Schema-valid results for all demo companies/dates; attribution invariant tested; SVB/BBBY/WeWork case studies show their filed signals |
| 3 Backend | ✅ | Full journey integration test (auth → job → report → history → alerts → exports → API key → RBAC) |
| 4 Frontend | ✅ | All pages built; report page test (202 → poll → render); code-split bundle |
| 5 NLP (M1, M2) | ✅ M1 · M2 as rules | M1 fine-tuned transformer vs baselines; M2 news event classes ship as documented rules (no hand-labelled set yet) |
| 6 Reviews (M3) | ✅ | Company-held-out macro-F1 0.629 vs VADER 0.447; index vs true rating r = 0.91; 33 employers mapped to SEC CIKs |
| 7 Risk/anomaly/forecast | ✅ | M7 beats Altman/Ohlson; M5b beats Beneish on restatements; M5a rejected by the gate (rule serves); M6 beats naive/seasonal-naive/ETS |
| 8 MLOps | ✅ | MLflow tracking + registry aliases, promotion gate, model cards, PSI drift job, scheduled/drift retraining |
| 9 Evaluation & docs | ✅ | Report, viva guide, API and product docs |

## Resolved decisions (2026-10-05)

| # | Decision |
|---|---|
| D1 | **Markets:** US SEC filers first. All market-specific code sits behind `MarketProvider` and canonical schemas, so NSE/BSE is a plug-in later (DATA_STRATEGY §2). |
| D2 | **Employee reviews:** a public Kaggle Glassdoor dataset behind `ReviewSource`. No scraping. |
| D3 | **LLM:** not required. The template explanation provider is the default. Claude/OpenAI providers are optional (ARCHITECTURE §8). |
| D4 | **Team/scope:** small student team, complete MVP first, ML **not** simplified. Cuttable items are only those listed under "Optional" below. |
| D5 | **Demo universe:** 9 current companies (healthy + mixed) and 2–3 historical distress case studies analysed as of dates before the event (DATA_STRATEGY §3). |

## Milestones

- **M-A, end-to-end slice (after Phase 4):** search → analyze → explainable report in the UI, on real
  recorded SEC data, with the Financial + Events pillars, peer clustering, and MLflow in use.
- **M-B, ML MVP (after Phase 7):** every pillar and every model in ML_PIPELINE §4 is live, with evaluation tables.
- **M-C, project complete (after Phase 9):** MLOps hardening, backtest, report and viva material.

---

## Phase 0: Design and foundations  ← *current*

- Design docs: architecture, data strategy, ML pipeline/MLOps, scoring, roadmap. ✅
- Database schema as a Flyway migration (`V1__init.sql`). ✅
- Skeletons: FastAPI `/health`, Spring Boot (Actuator + Flyway), React/Vite/Tailwind shell.
- `infra/docker/docker-compose.yml`: postgres, redis, mlflow, ml-service, backend, frontend.
- Per-service lint/test commands. GitHub Actions CI.

**Exit:** every service builds and its tests pass. A Testcontainers test applies `V1__init.sql` to real
Postgres. `docker compose up` brings up healthy services.

## Phase 1: SEC data foundation

- `UsSecProvider`: name/ticker/former-name resolution (rapidfuzz), submissions, companyfacts, 8-K items.
  Includes rate limiting, a contact `User-Agent` and a Redis cache.
- `mappings/us_gaap.yaml` → canonical facts. Point-in-time fact store (parquet), TTM/YoY builders.
- `mappings/sec_8k_items.yaml` → canonical events.
- Bulk ingestion of `companyfacts.zip` + submissions → reference universe, and sector peer statistics per as-of date.
- `record_sample` → `data/sample/` for the 12-company demo universe, plus `MANIFEST.json`.

**Exit:** facts for Apple match the 10-K figures in hand-checked tests. A point-in-time test proves no
`filed > as_of` leakage. Demo snapshot recorded.

## Phase 2: Scoring engine + contract (ML service)

- Pydantic `AnalysisResult` + exported JSON Schema.
- Financial pillar (standard + bank variant), Events pillar, peer percentiles, composite, confidence,
  additive attribution, caps, bands, warning signals.
- **M4 peer clustering**, trained through the pipeline and logged to MLflow. This is the first use of the MLOps path.
- Template explanation provider. `/v1/resolve`, `/v1/analyze`, `/v1/models`.

**Exit:** a schema-valid result for every demo company and as-of date. The attribution invariant and ratio math are
unit-tested. The SVB and BBBY as-of reports show their filed warning signals.

## Phase 3: Backend API (Spring Boot)

- JPA entities over V1, ML client (timeouts, retry), async jobs with dedup, report persistence,
  history, compare, JWT auth (register/login), watchlists, alerts, OpenAPI, RFC 7807 errors.

**Exit:** search → analyze → poll → report → history works over HTTP. Testcontainers + WireMock integration tests pass.

## Phase 4: Frontend MVP  ✅ *M-A*

- Search with disambiguation (including former names), company report: Overview (gauge, band, confidence,
  pillar bars, summary, signals, data-coverage panel), Financials, Events timeline, and a "Why?" drawer with evidence
  links. Case-study banner for historical as-of reports. Disclaimer on every report.
- Auth pages, watchlist, compare view, "Models" page listing model cards.

**Exit:** a full demo walkthrough with no API keys. A Playwright smoke test passes.

## Phase 5: NLP for news (M1, M2)

- GDELT `NewsSource`, de-duplication, sentiment model training (baselines → fine-tuned transformer),
  ECHO headline labelling set, event classifier. News pillar and sentiment UI tab.

**Exit:** evaluation tables (model vs baselines) in MLflow and the docs. The model passes the promotion gate.

## Phase 6: Employee reviews (M3)

- Kaggle ingestion script, company mapping file, review classifier, BERTopic themes, Employee
  Sentiment Index with CI. Workforce pillar and Workforce tab.

**Exit:** company-held-out evaluation beats the baselines. The index correlates with true ratings, and that correlation is reported.

## Phase 7: Risk, anomaly, forecasting (M5, M6, M7)  ✅ *M-B*

- Distress model (time split, calibration, SHAP, vs Altman/Ohlson), financial and market anomaly detection,
  fundamentals forecasting with intervals, Market pillar, Risk and Market tabs, history backfill.

**Exit:** the ML_PIPELINE §8 tables are produced. Every dashboard number is tagged ML/Stat/Rule.

## Phase 8: MLOps hardening

- Registry aliases + automated promotion gate, export with model cards, drift/freshness monitoring job
  and the UI view, CI training smoke tests, `pipelines.run all` reproducibility check.

**Exit:** a clean clone + `pipelines.run all` reproduces the champion metrics within tolerance.

## Phase 9: Evaluation and documentation  ✅ *M-C*

- Health-score backtest, ablation, weight calibration (M8b), case-study write-ups, error analysis,
  `docs/report/`, `docs/viva/`, `docs/api/`.

---

## Optional (after M-B, in priority order)

1. Claude/OpenAI explanation providers + grounding validator.
2. Scheduler: watchlist refresh and `SCORE_DROP` alerts.
3. Job-board hiring snapshots (Greenhouse/Lever).
4. NSE/BSE `MarketProvider` (`ind_as.yaml`, SEBI disclosure mapping).
5. SaaS features: organisations, API keys, usage plans, a public API with rate limits.
6. GDELT raw-file news backfill for the case-study windows.

## Main risks

| Risk | Mitigation |
|---|---|
| Free price sources lack delisted tickers | The Market pillar degrades to "unavailable" for case studies. The distress model is accounting-only. |
| Few distress positives | PR-AUC, class weights, a long training window (2010–2019), and honest reporting of confidence intervals |
| CPU-only transformer training is slow | DistilRoBERTa-sized models and a capped dataset size, or a free Colab GPU. Hardware is recorded in the model card. |
| Look-ahead leakage | `filed`-date discipline, as-of peer rebuilds, a leakage unit test |
| Dataset licences (L1–L4) | Resolved before the phase that needs them. Raw third-party data is never committed. |
| Scope | Phase gates. Only the "Optional" list may be cut. |
