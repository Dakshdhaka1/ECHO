# ECHO — Enterprise Corporate Health Observatory

**B.Tech (AI & ML) project report.** All results in this report come from the code in this repository and
can be regenerated with `python -m pipelines.run all`. Figures referenced below are written to
`ml-service/reports/<model>/` by the training pipelines, and every number has a matching model card under
`ml-service/artifacts/<model>/<version>/model_card.json`.

---

## 1. Problem statement

Understanding the real condition of a company means reading information scattered across many sources:
financial statements, regulatory filings, stock-market behaviour, news, hiring and employee sentiment. Each
source shows only part of the picture, reading them all by hand is slow, and cross-source warning patterns
(for example a late filing followed by an auditor change and collapsing margins) are easy to miss.
Investors, analysts, job seekers, suppliers and researchers all need a fast, comprehensive and *honest* view
of a company's publicly observable health.

## 2. Objectives

1. Build an end-to-end platform that resolves a company name and collects legitimate public data about it.
2. Apply genuine, evaluated ML/NLP models (not only an LLM API) to that data: sentiment analysis, distress
   prediction, anomaly detection, forecasting and segmentation, each compared with a baseline on held-out data.
3. Combine the signals into a transparent 0–100 Corporate Health Score with exact factor attribution, and
   explain the ML risk estimate with SHAP.
4. Enforce point-in-time correctness so that historical analyses (case studies) use only data that was public
   at the time.
5. Run the models with a production-style MLOps lifecycle: tracking, versioning, a promotion gate, model cards,
   drift monitoring and scheduled retraining.
6. Deliver it as a usable SaaS product (web dashboard, accounts, watchlists, alerts, exports, API, plans), while
   never claiming certainty or giving investment advice.

## 3. System architecture

Three services and three data stores (full description in `docs/architecture/ARCHITECTURE.md`):

- **Frontend** (React 19, Vite, Tailwind, Recharts) - search, the report dashboard with nine tabs, compare,
  watchlists, alerts, model cards, pricing, account/API keys, admin & MLOps.
- **Backend** (Spring Boot 4, Java 17) - JWT + API-key security with roles and plans, the company registry,
  **asynchronous analysis jobs** (deduplicated by a partial unique index), report storage as JSONB, score
  history, watchlist alerts, PDF/CSV export, OpenAPI docs, RFC 7807 errors, schedulers.
- **ML service** (FastAPI, Python 3.12) - data providers (SEC, GDELT, prices, reviews), the point-in-time
  feature builder, model inference, the scoring engine, warning rules, the explanation layer, monitoring and a
  retraining endpoint.
- **PostgreSQL** (application data), **Redis** (caching, rate limits), **MLflow** (experiments and registry).

One versioned JSON document, `AnalysisResult`, is the contract between the ML service and the backend. The
backend integration test replays a real recorded `AnalysisResult` through the whole API.

## 4. Datasets

| Dataset | Source and licence | Size used | Used for |
|---|---|---|---|
| SEC XBRL company facts (bulk `companyfacts.zip`) | SEC EDGAR, public domain | 1.4 GB zip → **11.3 M canonical facts**, 41,500 periodic filers | Financial features, peer statistics, forecasting, anomaly detection |
| SEC submissions (bulk `submissions.zip`) | SEC EDGAR, public domain | 1.6 GB zip → **3.25 M filings** incl. 1.99 M 8-Ks with item codes | Events, **distress labels (8-K Item 1.03)**, restatement labels (Item 4.02) |
| Distress dataset (derived) | from the two above | **62,437** point-in-time 10-K rows, 2010–2024, **553 positives (0.89 %)** | M7 training/evaluation, M4, M5b |
| twitter-financial-news-sentiment | Hugging Face `zeroshot`, MIT | 9,543 train / 2,388 test | M1 training, in-domain test |
| Financial PhraseBank v1.0 (AllAgree) | CC BY-NC-SA 3.0 (evaluation only) | 2,264 sentences | M1 primary out-of-domain test |
| IBM daily prices 1999–2026 | Alpha Vantage public demo key (not redistributed) | ~6,700 trading days | M5a training/evaluation |
| Demo-universe prices | Alpha Vantage free key (not redistributed) | weekly adjusted history (to 1999) + last 100 daily bars for 9 companies, 3 sector ETFs and SPY | Market pillar, daily anomalies |
| GDELT DOC 2.0 headlines | GDELT, free with citation (metadata only) | last ~90 days for demo companies | News pillar at inference |
| Kaggle Glassdoor Job Reviews | Kaggle (no licence listed → academic use only, not redistributed) | 838,566 reviews, 428 employers, 2008–2021; 33 employers mapped to SEC filers | M3 training/evaluation, Workforce pillar |

**Demo snapshot.** `data/sample/` holds *recorded real data* for 12 companies (9 current, 3 historical
distress case studies), with a SHA-256 manifest, so the system runs offline with no keys. No data in the demo
is synthetic; synthetic data appears only in the anomaly-injection benchmarks and is labelled there.

## 5. Methodology

### 5.1 Data cleaning and the canonical schema

XBRL tags differ across companies and years (for example `Revenues` vs
`RevenueFromContractWithCustomerExcludingAssessedTax`). `mappings/us_gaap.yaml` maps ranked tag lists to 31
canonical items. Each reported value is kept with the date it was **first filed**, and restatements are kept as
separate values. Facts with impossible dates (XBRL typos such as year 0201) are dropped.

### 5.2 Point-in-time feature engineering

`pipelines/features/financial.build(facts, as_of)` is the single feature builder shared by training and
inference. For any date it uses only facts with `filed ≤ as_of`, choosing the best-ranked tag and then the
latest version of each value.

- **Quarterly derivation.** Cash-flow items are often reported only year-to-date, so quarters are derived as
  differences of consecutive cumulative values. Q4 is computed as FY − 9M.
- **Trailing twelve months (TTM).** Built from four consecutive quarters, or the fiscal year when that aligns.
- **27 financial features** across six groups:
  - profitability: net margin, ROA, EBIT/assets, gross margin;
  - liquidity and solvency: current ratio, cash/assets, debt/equity, liabilities/assets, interest coverage, negative equity;
  - cash flow: OCF/liabilities, FCF margin, quarters of negative FCF;
  - growth: revenue YoY, Δ margin, Δ current ratio, Theil–Sen 8-quarter revenue slope;
  - classic scores: Altman Z″ components, Ohlson O, Piotroski F, Beneish M;
  - market proxy and timeliness: public float/liabilities (from the 10-K cover page), filing lag in days.
- **9 event features.** Decayed counts (180-day time constant) of restatements, auditor changes, officer
  changes, restructurings, impairments, delisting notices, debt accelerations, late-filing notices (NT 10-K/Q)
  and cyber incidents.
- **8 Beneish forensic indices** for the anomaly model.

The NumPy implementation computes about 70 snapshots per second per core. A unit test asserts that no input
used for a row was filed after that row's date.

### 5.3 The health score (statistical, transparent)

Five pillars, each a weighted mean of factor scores:

| Pillar | Weight |
|---|---|
| Financial | 0.30 |
| Market | 0.20 |
| News | 0.20 |
| Workforce | 0.15 |
| Events & governance | 0.15 |

- **Factor scores** are sector-peer percentiles taken as of the analysis date. Peer tables are rebuilt from all
  filers for every date used.
- **Guard-rails** cap a factor's score when its absolute level signals distress. For example, an Altman Z″
  below 1.1 caps that factor at 20, even when its peers are worse.
- **Banks** (SIC 6000–6399) get their own Financial-pillar factors: equity/assets, unrealised securities
  losses/equity, deposit growth, loans/deposits and ROA.
- **Missing pillars** are excluded and the remaining weights renormalised. Confidence is
  Σ weight × coverage, and below 0.40 no score is shown.
- **Exact attribution.** Every factor's impact is `w̃_p · a_f · (s_f − 50)`, and the impacts sum exactly to
  score − 50. A unit test enforces this.

### 5.4 ML models — algorithms and justification

| # | Task | Algorithm and why | Baselines |
|---|---|---|---|
| M1 | Headline sentiment | **DistilRoBERTa fine-tuned** (82 M params, 3 epochs on CPU, early stopping on validation macro-F1). A transformer captures negation and context that lexicons miss; DistilRoBERTa fits a laptop CPU and was exported to **int8 ONNX** for torch-free serving. | VADER (lexicon), TF-IDF word+char n-grams + logistic regression, off-the-shelf FinBERT |
| M7 | 12-month distress probability | **LightGBM** gradient boosting. It suits tabular data with missing values, non-linear ratio effects and rare positives. Optuna tuned it (30 trials on validation PR-AUC), it uses class weighting, and **Platt calibration** maps scores to probabilities. Platt is monotone, so ranking is preserved. LR, RF and XGBoost were also trained. | Altman Z″, Ohlson O (classic accounting-based models) |
| M5b | Financial-statement anomaly | **Isolation Forest** on signed-log, robust-scaled forecast-free forensic indices. It is unsupervised because manipulation labels are rare and late. | Beneish M-score |
| M5a | Trading anomaly | **Isolation Forest** on robust z-scores (return, volume, range, gap) vs a trailing 60-day window | max \|robust z\| rule |
| M6 | Revenue / OCF forecasting | **Global LightGBM** across ~4,000 companies. It uses direct multi-horizon (1–4 quarters) scale-free lag features and a Huber loss, and **split-conformal 80 % intervals** give distribution-free coverage. | naive, seasonal naive, ETS (Holt-Winters damped) per series |
| M4 | Segmentation | **K-means** on quantile-normalised ratios, with k = 4–7 chosen by silhouette; a GMM was compared. Clusters are named by a documented centroid rule (Stable / Growth / Watchlist / High Risk). | sector-only grouping |
| M3 | Employee reviews | TF-IDF + LR on headline + pros + cons, with a company-grouped split; NMF complaint themes; Employee Sentiment Index with bootstrap CI | VADER |
| M2 | News event type | Keyword rules (Kind = Rule), honestly labelled. A trained classifier needs a hand-labelled set (future work). | — |

### 5.5 Leakage controls

- **Time-based splits** for all temporal models:
  - M7: train 2010–2019, validation 2020–2021, test 2022–2024;
  - M5b: train ≤ 2019, test 2020–2024;
  - M5a: ≤ 2015, then later years;
  - M6: rolling origin, with targets up to 2022 for training, 2023 for conformal calibration, and 2024–H1 2025 for test.
- **Train-only fitting.** Winsorisation, scalers, calibration and thresholds are fitted on training or validation
  data only, and the test set is used once.
- **No train/eval contamination.** FinBERT is *not* evaluated on PhraseBank, because it was trained on it.
- **Company-grouped split** for the review data.

### 5.6 Training pipeline and MLOps

`python -m pipelines.run <model>` runs ingestion (cached) → cleaning → features → training → evaluation →
export, from a YAML config with a fixed seed. Each run:

- logs parameters, metrics, the git SHA, the data-manifest hash and figures to **MLflow**, and registers a model;
- writes `artifacts/<model>/<version>/` with a **model card** (data, metrics vs baseline, intended use,
  limitations, licences, hardware);
- passes through the automated **promotion gate**: it must beat the baseline *and* the current champion by a
  margin, have a complete card, and pass an inference smoke test on the exported files. Only then does it
  become `champion` (MLflow alias plus a `CHAMPION` pointer that the API hot-reloads).

**Monitoring.** Each analysis logs model inputs to SQLite, and a job computes the population stability index
(PSI) per feature against the training reference histograms stored with the model (alert > 0.2), plus
prediction drift and data freshness.

**Retraining.** The backend scheduler retrains monthly, re-runs drift monitoring weekly, and retrains on drift.
Admins can also retrain from the UI. The gate stops a worse model from replacing the champion, and this
happened in practice twice:

- `distress` v1 (isotonic calibration) was replaced by v2 (Platt), which ranked better;
- `market_anomaly` was never promoted (§6.4).

**Reproducibility check.** Three models were re-trained from scratch with the same pipeline and seed: news
sentiment on the host, and financial anomaly and segmentation inside the Docker container through the admin
retrain endpoint. Each reproduced its champion's primary metric exactly (macro-F1 0.8948, restatement ROC-AUC
0.6977, silhouette 0.2246). The gate kept each as a challenger, because a model that does not *beat* the
champion is never promoted.

## 6. Results

### 6.1 M1 — news sentiment (macro-F1, test sets never used in training or selection)

| Model | Financial PhraseBank (primary) | Twitter-fin test |
|---|---|---|
| VADER | 0.487 | 0.447 |
| TF-IDF + logistic regression | 0.679 | 0.764 |
| FinBERT (off the shelf) | — (trained on it) | 0.668 |
| **DistilRoBERTa fine-tuned (champion)** | **0.895** (accuracy 0.912) | **0.848** (accuracy 0.881) |

- **Selection.** On validation, the transformer scored 0.825 macro-F1 against 0.756 for TF-IDF.
- **Training curve.** Validation macro-F1 was 0.803 after epoch 1 and 0.825 after epoch 2.
- **Confusion matrix.** `ml-service/reports/news_sentiment/confusion_phrasebank.png`.

### 6.2 M7 — 12-month distress (test 2022–2024: 13,345 filings, 159 bankruptcies, base rate 1.19 %)

| Model | ROC-AUC | PR-AUC (primary) |
|---|---|---|
| Altman Z″ (baseline) | 0.754 | 0.024 |
| Ohlson O (baseline) | 0.745 | 0.022 |
| Logistic regression | 0.824 | 0.063 |
| Random forest | 0.886 | 0.099 |
| XGBoost | 0.875 | 0.103 |
| **LightGBM + Platt (champion)** | **0.882** (90 % CI 0.861–0.904) | **0.123** (90 % CI 0.094–0.161) |

- **Versus baselines.** PR-AUC is **5.2× Altman Z″** and 10× the base rate. LightGBM was chosen on
  *validation* PR-AUC (0.136); random forest has a marginally higher test ROC-AUC but lower PR-AUC.
- **Calibration.** Brier score 0.0112 with Platt, 0.0112 with isotonic, and 0.0162 for raw class-weighted scores.
  The risk bands are monotone in the observed outcome rate:

  | Risk band | Test companies | Observed bankruptcy rate |
  |---|---|---|
  | Low | 11,349 | 0.33 % |
  | Moderate | 1,268 | 3.5 % |
  | Elevated | 593 | 9.3 % |
  | High | 135 | 16.3 % |

- **Confusion matrix** at the validation-chosen threshold (0.153): TP 14, FP 45, FN 145, TN 13,141. Precision
  is 0.24 and recall 0.09. This is a deliberately cautious operating point. The product shows probabilities
  and bands rather than yes/no predictions.
- **Explainability.** SHAP mean |contribution| ranks company size, Ohlson O, ROA, public float/liabilities,
  interest coverage, EBIT/assets, leverage and filing lag highest (`shap_summary_test.png`). Every report shows
  per-company SHAP drivers.
- **Ablation** (test PR-AUC after dropping a feature group, full model 0.123):

  | Group dropped | Test PR-AUC |
  |---|---|
  | market proxy and size | 0.099 |
  | profitability | 0.107 |
  | events / timeliness | 0.111 |
  | classic scores | 0.112 |
  | cash flow | 0.113 |
  | growth | 0.117 |
  | liquidity / solvency | 0.130 |

  Liquidity/solvency is redundant with the classic scores, and dropping it slightly *helped*, which is a
  candidate simplification.

### 6.3 M5b — financial-statement anomaly (test 2020–2024)

| Model | Later restatement (8-K 4.02) ROC-AUC (primary) | Lift in top 5 % | Injected-distortion PR-AUC |
|---|---|---|---|
| Beneish M-score | 0.497 | 1.71× | 0.063 |
| **Isolation Forest (champion)** | **0.698** | **2.45×** | 0.029 |

The unsupervised model ranks statements that are later restated well above chance, while the classic M-score
does not. The injection benchmark distorts exactly the indices the M-score is a linear function of, so it
favours the baseline by construction. It is reported for completeness, and the real-outcome metric is the
primary metric (ML_PIPELINE §4).

### 6.4 M5a — trading anomaly (IBM, test after 2015)

On injected shocks over ordinary days, the robust max-|z| rule reached a PR-AUC of **0.974** and the Isolation
Forest 0.406. On real earnings-release days (8-K Item 2.02) both flag **45.7 %** of events in their top-5 %
scores, a **9.1× lift**. The ML model did **not** beat the statistical rule, so the gate kept it as a challenger
and the service uses the rule, labelled `Stat`. This is a deliberate negative result: for univariate spikes a
robust z-score is near-optimal.

### 6.5 M6 — fundamentals forecasting (targets 2024 – H1 2025, about 20 k origin-horizon pairs)

| Target | Naive | Seasonal naive | ETS* | **Global LightGBM** | 80 % interval coverage |
|---|---|---|---|---|---|
| Revenue (MASE) | 4.31 | 4.29 | 1.54 | **4.14** (1.43*) | 82.6 % |
| Operating cash flow (MASE) | 1.76 | 1.57 | 1.45 | **1.40** (1.30*) | 81.5 % |

\* on the 1,500-origin subset where ETS was fitted.

The model beats every baseline on both targets, and the conformal intervals hit their nominal 80 %. The high
absolute MASE for revenue comes from a few near-constant series with tiny scaling denominators; the ETS-subset
numbers show the typical case.

### 6.6 M3 — employee-review sentiment (company-grouped split: 108k / 24k / 18k reviews, 296 / 64 / 64 employers)

| Model | Macro-F1 (employers never seen in training) | Accuracy |
|---|---|---|
| VADER | 0.447 | — |
| **TF-IDF + logistic regression (champion)** | **0.629** | 0.697 |

Labels come from star ratings (1–2 negative, 3 neutral, 4–5 positive). Neutral is the hard class (F1 0.42):
three-star reviews mix praise and complaints. The **Employee Sentiment Index** (mean P(pos) − P(neg) per
company-quarter, bootstrap 90 % CI) correlates **r = 0.91** (Spearman 0.90) with the true mean star rating
across 407 held-out company-quarters, so the index is a faithful summary of the reviews.

NMF over the "cons" text gives the complaint themes shown per company: workload & staffing, pay & benefits,
management, career growth, work-life balance, and promotion difficulty. v1's themes included filler topics built
from review boilerplate ("cons / don / good"). v2 added review-specific stop words and was **manually promoted
with an audited reason** (`python -m pipelines.mlops promote`), because its classifier metrics were identical,
so the gate could not see the improvement.

*Observation:* Microsoft's index rises from about +0.15 (2008–2013) to +0.58 (2021), consistent with its widely
reported culture change after 2014; the 2014 restructuring 8-K (Item 2.05) appears in the same tab.

### 6.7 M4 — segmentation (4,027 companies' latest 10-K in 2024)

K-means with k = 4 had silhouette **0.225**, against −0.074 for sector-only grouping and 0.172 for a GMM. The
Davies–Bouldin index was 1.48 and year-over-year stability (ARI) **0.85**.

The segments separate risk without using labels: the subsequent 12-month bankruptcy rate was **5.2 %** for
High Risk, 1.2 % for Growth and **0.13 %** for Stable. Figure: `segments_pca.png`.

## 7. Case studies (point-in-time, using only data filed by the date shown)

| Company, as of | Score | What the public data showed |
|---|---|---|
| Apple, latest | 68 Stable* | net margin 27.6 %, FCF margin 29.3 %, Piotroski 8/9; distress probability 0.04 % |
| Bed Bath & Beyond, 2023-01-31 (Ch. 11 in Apr 2023) | **38 Weak** | revenue −26 %, Piotroski 1/9, current ratio 0.73, negative equity, late-filing notice; distress probability **7.8 %** (Elevated, about 6× base rate) |
| WeWork, 2023-05-31 (Ch. 11 in Nov 2023) | **28 Weak** | Altman Z″ −4.49, current ratio 0.37, net margin −64 %, delisting notice, late filing |
| Meta, 2022-12-31 | Market pillar 8/100 | share price **64 % below its 52-week high**, 12-month return −36.5 % vs the tech sector ETF, 80 % volatility; `DRAWDOWN` signal (the 2022 crash), while financials remained strong |
| SVB Financial, 2022-12-31 (failed Mar 2023) | **47 Watch** | bank variant: **unrealised securities losses = 121 % of equity** was the largest drag |

\*Apple's score includes a near-neutral News pillar (36 headlines); with Financial and Events alone it was 77.

**Error analysis.**

- **Bed Bath & Beyond.** Its last 10-K was filed 367 days before the bankruptcy, so under the strict
  12-month label that filing counts as a negative.
- **SVB.** It was a bank, so the distress model does not apply. Its Watch band (rather than Weak) shows that
  balance-sheet ratios alone understated the run risk; deposit flight happened within days and is not visible
  in quarterly filings.
- **WeWork.** Its real-estate SIC code puts it outside the distress model's training population, so only the
  score and rules flag it.

## 8. Explainable AI

Three explanation mechanisms, from simple to model-specific:

1. **Exact additive attribution** of the health score: the "Why this score" tab shows the factor-impact chart,
   with every factor's value, peer percentile, score, impact and source link.
2. **SHAP (TreeSHAP)** for the distress model: per-company drivers on the Risk & ML tab, plus a global summary
   plot.
3. **Anomaly drivers**: the features with the largest standardised deviations.

The executive summary is generated from these structured facts by a deterministic template. An optional Claude
provider is available, but its output must pass a grounding validator: every number must appear in the facts,
every evidence ID must exist, and no advice language is allowed. Otherwise the template is used.

## 9. Limitations

- **Expert weights.** The pillar weights are set by hand, not learned. Backtest calibration of the weights is
  future work.
- **Rare-event model.** Distress is predicted only through filed bankruptcies, so companies that stop filing
  before failing are missed. Precision at a usable recall is modest (§6.2), and probabilities can drift with
  the credit cycle; PSI monitoring watches for that.
- **Sparse news history.** The GDELT DOC API covers only about 3 months and throttles heavily, so historical
  case studies have no news pillar.
- **Prices.** The free price tier gives full weekly but only 100 days of daily history, and no delisted
  tickers, so the historical case studies (except Meta) have no Market pillar and the distress model stays
  accounting-only.
- **Employee reviews.** These come from an academic-use dataset that ends in June 2021 and covers only 33 SEC filers, so the Workforce pillar is historical (down-weighted by freshness) and missing for most companies.
- **News event types** come from rules (M2), not a trained model.
- **Relative scoring.** Percentile scores are peer-relative; the absolute guard-rails mitigate this.
- **Correlation, not causation.** ECHO is not financial advice.

## 10. Future scope

- **Learned weights.** Calibrate pillar weights from backtests; add a health-score backtest across all 553
  bankruptcies.
- **Better labels.** Hand-label news events (with Cohen's κ) and train the M2 classifier; add going-concern
  labels from EDGAR full-text search.
- **Markets.** Add an NSE/BSE `MarketProvider` (Ind-AS mappings).
- **Licensed data.** Licensed price and review sources; job-board hiring snapshots.
- **Product.** Teams, SSO and webhook alerts; a portfolio view; LLM long-form reports under the grounding validator.

## 11. References

1. Altman, E. I. (1968). Financial ratios, discriminant analysis and the prediction of corporate bankruptcy. *Journal of Finance*, 23(4).
2. Ohlson, J. A. (1980). Financial ratios and the probabilistic prediction of bankruptcy. *Journal of Accounting Research*, 18(1).
3. Piotroski, J. D. (2000). Value investing: the use of historical financial statement information. *Journal of Accounting Research*, 38.
4. Beneish, M. D. (1999). The detection of earnings manipulation. *Financial Analysts Journal*, 55(5).
5. Ke, G. et al. (2017). LightGBM: a highly efficient gradient boosting decision tree. *NeurIPS*.
6. Chen, T. & Guestrin, C. (2016). XGBoost: a scalable tree boosting system. *KDD*.
7. Lundberg, S. & Lee, S.-I. (2017). A unified approach to interpreting model predictions (SHAP). *NeurIPS*.
8. Liu, F. T., Ting, K. M. & Zhou, Z.-H. (2008). Isolation Forest. *ICDM*.
9. Sanh, V. et al. (2019). DistilBERT, a distilled version of BERT. *NeurIPS EMC² workshop*; Liu, Y. et al. (2019). RoBERTa.
10. Malo, P. et al. (2014). Good debt or bad debt: detecting semantic orientations in economic texts (Financial PhraseBank). *JASIST*.
11. Araci, D. (2019). FinBERT: financial sentiment analysis with pre-trained language models. arXiv:1908.10063.
12. Hutto, C. & Gilbert, E. (2014). VADER: a parsimonious rule-based model for sentiment analysis. *ICWSM*.
13. Platt, J. (1999). Probabilistic outputs for support vector machines. *Advances in Large Margin Classifiers*.
14. Vovk, V., Gammerman, A. & Shafer, G. (2005). *Algorithmic Learning in a Random World* (conformal prediction).
15. Hyndman, R. J. & Koehler, A. B. (2006). Another look at measures of forecast accuracy (MASE). *IJF*, 22(4).
16. Akiba, T. et al. (2019). Optuna: a next-generation hyperparameter optimization framework. *KDD*.
17. Siddiqi, N. (2006). *Credit Risk Scorecards* (population stability index).
18. U.S. SEC. EDGAR APIs and Financial Statement data (XBRL); Form 8-K item instructions.
19. Leetaru, K. & Schrodt, P. (2013). GDELT: Global Data on Events, Location and Tone.
