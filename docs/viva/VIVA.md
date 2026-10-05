# ECHO — Viva Guide

## Before the viva (10 minutes)

1. `docker compose --env-file .env -f infra/docker/docker-compose.yml up -d` and wait until `docker compose ps`
   shows the services healthy. Open http://localhost:5173.
2. Register `admin@echo.local` so the Admin & MLOps page is available, and register a second, normal account
   in a private window.
3. Open the reports once beforehand so they are cached: **Apple** (latest), **Bed Bath & Beyond as of
   2023-01-31**, **SVB as of 2022-12-31** and **WeWork as of 2023-05-31**.
4. Keep these open in tabs:
   - MLflow (http://localhost:5000);
   - Swagger (http://localhost:8080/api/swagger-ui);
   - `docs/report/REPORT.md`;
   - `ml-service/reports/distress/roc_pr_test.png` and `shap_summary_test.png`.

## Demo script (8–10 minutes)

| # | Show | Say |
|---|---|---|
| 1 | Landing page → search "apple computer" | Search resolves current names, tickers *and former names* against SEC EDGAR. Everything shown comes from recorded real public data; nothing is simulated. |
| 2 | Apple report → **Overview** | 0–100 score, band, **confidence = data coverage**. Missing pillars (no prices without a key) are shown as missing, never filled with defaults. The summary is generated from the same factor impacts. |
| 3 | **Why this score** tab | Every factor's exact contribution in points: 50 + Σ impacts = the score. Peer percentiles are computed against every SEC filer in the same sector, *as of the report date*. Each row links to the filing. |
| 4 | Bed Bath & Beyond **as of 2023-01-31** | A point-in-time case study: only data filed before that date. Score 38 (Weak), Piotroski 1/9, revenue −26 %, late-filing notice. The **ML distress probability is 7.8 %**, about 6× the base rate, three months before the Chapter 11 filing. |
| 5 | **Risk & ML** tab (BBBY) | SHAP drivers of the LightGBM model: which features push the risk up (red) or down (blue). Next to them: segment (k-means), statement anomaly (Isolation Forest), forecasts with conformal intervals. |
| 5b | Meta **as of 2022-12-31**, Market tab | Point-in-time market data: the weekly adjusted history shows the 64 % drawdown from the 52-week high and a `DRAWDOWN` signal, Meta's real 2022 crash. |
| 6 | SVB **as of 2022-12-31** | Bank variant of the Financial pillar: **unrealised securities losses = 121 % of equity** is the largest drag, ten weeks before the failure. It also shows a limitation: the run on deposits happened faster than quarterly filings can show. |
| 7 | **News & sentiment** (Microsoft or Apple) | Headlines scored by our fine-tuned DistilRoBERTa, served as quantised ONNX. Thin coverage lowers confidence instead of swinging the score (shrinkage toward neutral). |
| 8 | **Models** page + sentiment playground | Model cards: test metric vs baseline and the gate decision. Type "Shares plunge after fraud probe" and get negative 0.99. Point out that the market Isolation Forest *failed* the gate. |
| 9 | Microsoft → **Workforce** tab | Employee Sentiment Index from 26,672 reviews scored by our review model (r = 0.91 with true star ratings), with a bootstrap CI and complaint themes (NMF). The index rises after 2014, Microsoft's reported culture change. |
| 9b | Watchlist → Re-analyse → Alerts; Compare | Async jobs, watchlist alerts on score drops, comparison chart plus table. |
| 10 | Pricing → switch to Pro → PDF export; Account → API key | SaaS layer: plan limits enforced server-side (403 plan-limit), PDF reports, API keys stored only as SHA-256 hashes. |
| 11 | Admin → run monitoring → retrain a model; MLflow | MLOps loop: PSI drift report, retraining with the promotion gate, runs and registry in MLflow. |

## Likely questions and answers

**1. Where is the AI/ML? Isn't the score just a formula?**
The score is a transparent formula on purpose, because no ground-truth label for "health" exists. The
ML is in the models that feed it and sit beside it:

- a fine-tuned transformer for sentiment (macro-F1 0.895 vs 0.679 for TF-IDF and 0.487 for VADER);
- a LightGBM distress model trained on 62k real filings with 553 real bankruptcies (PR-AUC 0.123 vs 0.024 for Altman Z″);
- Isolation Forest anomaly detection (restatement ROC-AUC 0.70 vs 0.50 for Beneish);
- a global LightGBM forecaster with conformal intervals;
- k-means segmentation.

Each model has a baseline, a held-out test set and a model card.

**2. Why LightGBM for distress, and why PR-AUC?**
The data is tabular, with missing values, non-linear ratio effects and only 0.9 % positives. Boosted trees
handle all of that natively, and Optuna tuned LightGBM on validation. PR-AUC is the primary metric because
with rare positives ROC-AUC looks good even for weak models. For context, Altman's ROC-AUC is 0.75 but its
PR-AUC is only 0.024.

**3. How do you avoid data leakage?**
- **Point in time.** Every feature uses only facts with `filed ≤ as_of` (a unit test asserts this), and
  restatements are applied only after their filing date.
- **Time splits.** Train 2010–19, validate 2020–21, test 2022–24.
- **Train-only fitting.** Winsorisation, calibration and thresholds are fitted on train or validation only.
- **No contamination.** FinBERT is not evaluated on PhraseBank because it was trained on it.

**4. Where do the bankruptcy labels come from?**
From SEC 8-K Item 1.03 ("Bankruptcy or Receivership") filings: 3,470 such filings by 1,832 companies. A
10-K row is labelled positive when an Item 1.03 follows within 365 days. Rows from companies already in
bankruptcy are dropped.

**5. Precision is only 0.24 at the chosen threshold. Is the model useless?**
Bankruptcy within 12 months is rare and hard to predict, so we present calibrated probabilities and risk
bands rather than yes/no answers. On the test set the High band's observed bankruptcy rate is 16.3 %, against
0.33 % for Low, which is a 49× separation. The threshold is shown only for the confusion matrix.

**6. What is calibration and why Platt instead of isotonic?**
Calibration makes a "5 %" mean 5 %. Isotonic regression is a step function, so it created ties and lowered
PR-AUC from 0.123 to 0.103. Platt scaling is monotone, which keeps the ranking, and its Brier score was the
same (0.0112). The promotion gate replaced v1 (isotonic) with v2 (Platt).

**7. How is the score explained?**
The pillar weights sum to 1, so H − 50 = Σ w̃·a·(s − 50) exactly. Each factor's impact is its contribution in
points, and a unit test checks the sum. For the ML distress estimate we show TreeSHAP values. The LLM summary
is optional and must pass a grounding check: numbers must come from the facts, evidence IDs must exist, and
no advice words are allowed.

**8. What does SHAP tell you here?**
Globally, the most important features are size, Ohlson O, ROA, public float/liabilities, interest coverage
and filing lag (late filers are riskier). Locally, each report lists the features that pushed that company's
estimate up or down, in log-odds.

**9. Why did a model fail, and is that bad?**
The market Isolation Forest scored 0.41 PR-AUC on injected shocks against 0.97 for a robust z-score rule.
For single-day spikes a robust z-score is near-optimal. The gate refused to promote the ML model, so the
service uses the rule and labels it "Stat". That is the gate doing its job.

**10. How does sentiment training work on a CPU?**
DistilRoBERTa (82M parameters) was fine-tuned for 3 epochs, batch 32, max length 64, AdamW with linear warmup,
taking about 10 minutes per epoch on 16 threads, with early stopping on validation macro-F1. It was then
exported to ONNX and quantised to int8 (~80 MB), so serving needs only onnxruntime and tokenizers, not PyTorch.

**11. How do you know the forecast intervals are right?**
They come from split-conformal prediction: residual quantiles on a 2023 calibration set, applied per horizon.
Empirical 80 % coverage on the 2024–25 test set was 82.6 % for revenue and 81.5 % for operating cash flow.
MASE beats naive, seasonal naive and per-series ETS.

**12. What is MLOps in this project concretely?**
- **Pipeline.** One command per model, YAML configs, fixed seeds and SHA-256 data manifests.
- **Tracking.** MLflow records runs, metrics, figures and the git SHA, and holds the registry with champion/challenger aliases.
- **Promotion gate.** A model must beat its baseline and the current champion, have a complete card and pass a smoke test.
- **Export.** Model cards ship with the artifacts, and the API hot-reloads new champions.
- **Monitoring.** A PSI drift job compares live inputs with the training reference histograms.
- **Retraining.** Scheduled monthly, triggered by drift, or started manually from the admin UI.

**13. Is the data collection legal and ethical?**
Only documented APIs and published datasets are used: SEC (public domain), GDELT headline metadata (never
article bodies), MIT- and CC-licensed text datasets, and an academic-use review dataset the user downloads.
There is no scraping of LinkedIn, Glassdoor, Indeed or Yahoo. Every report carries a disclaimer, and the
product never gives buy/sell advice.

**14. What are the main limitations?**
- The pillar weights are set by hand.
- Bankruptcies of companies that stop filing are missed.
- News history covers only 3 months, and GDELT throttles heavily.
- The free price tier has full weekly but only 100 days of daily history and no delisted tickers (so BBBY, SVB and WeWork have no market pillar).
- The review data is academic-use only, ends in June 2021, and covers 33 SEC filers.
- News event types come from rules.
- Scores are peer-relative.

**15. How would this become a business?**
Free, Pro and Enterprise plans differ in fresh analyses, watchlists, history depth, PDF reports and API access
(see `docs/product/PRODUCT.md`). Next steps would be licensed review and price data, India (NSE/BSE) through the
same provider interface, team features, webhooks and portfolio monitoring.
