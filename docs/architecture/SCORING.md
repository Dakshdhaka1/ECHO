# ECHO — Health Score, ML Models and Evaluation

Status: **implemented** (2026-10-05, `ml-service/app/inference/scoring.py`). The weights, thresholds and bands below are expert-set starting values,
documented here so that none of them is hidden in code. Phase 9 of the build plan recalibrates them against the
backtest (§7). Model details are in [ML_PIPELINE.md](ML_PIPELINE.md).

---

## 1. Pillars

The health score is a weighted mean of five pillar scores, each from 0 to 100.

| Pillar | Weight | Question it answers | Main sources |
|---|---|---|---|
| **Financial** | 0.30 | Is the business solvent, profitable and liquid? | XBRL financial statements |
| **Market** | 0.20 | How is the market pricing the company relative to its sector? | Prices, volume, sector ETF |
| **News sentiment** | 0.20 | What is the recent tone of coverage, and is it getting better or worse? | GDELT / NewsAPI + FinBERT |
| **Workforce** | 0.15 | How are employees and hiring trending; is the company cutting? | Employee Sentiment Index (ML_PIPELINE M3), 8-K 2.05, layoff news, job boards (optional) |
| **Events & governance** | 0.15 | Have there been material adverse events? | 8-K items, classified news events, going-concern text |

---

## 2. Factors and normalisation

Each pillar is a weighted mean of **factor scores** (0–100). Raw factor values are converted into
scores as follows:

- **Peer percentile.** Most factors are scored by their percentile within a peer group (same sector
  or cluster, §5) taken from a reference universe that is recomputed nightly, and oriented so that
  higher is always healthier. `score = 100 × percentile`.
- **Absolute guard-rails.** If an entire sector is in distress, percentiles alone would hide it, so
  some factors also have absolute caps. Example: Altman Z in the distress zone caps that factor at 20,
  whatever its peer percentile.
- **Winsorise** raw values at the 1st and 99th percentiles before ranking.

| Pillar | Factor (within-pillar weight) | Raw value | Direction / guard-rail |
|---|---|---|---|
| Financial | Altman Z / Z″ (0.20) | Z for manufacturers, Z″ for others | ↑; Z < 1.81 (Z″ < 1.1) → cap 20 |
| | Piotroski F (0.15) | 0–9 | ↑; scored absolutely: `F/9 × 100` |
| | Revenue growth YoY, TTM (0.15) | % | ↑ |
| | Net margin, TTM (0.15) | % | ↑ |
| | Current ratio (0.10) | × | ↑; < 1.0 → cap 30 |
| | Debt / equity (0.10) | × | ↓; negative equity → 0 |
| | Free-cash-flow margin, TTM (0.15) | % | ↑ |
| Market | 6-month excess return vs sector ETF (0.30) | % | ↑ |
| | 12-month excess return vs sector ETF (0.20) | % | ↑ |
| | 90-day realised volatility (0.25) | annualised % | ↓ |
| | Drawdown from 52-week high (0.25) | % | ↓ |
| News | Recency-weighted sentiment, 90d (0.60) | −1…+1, half-life 14 days | ↑; mapped absolutely `50 × (1 + s)` |
| | Sentiment trend (0.25) | last 30d mean − prior 60d mean | ↑ |
| | Share of negative high-severity stories (0.15) | % | ↓ |
| Workforce | Employee Sentiment Index level (0.30) | −1…+1, latest quarter | ↑; absolute `50 × (1 + index)` |
| | Employee Sentiment Index trend (0.15) | 4-quarter Theil–Sen slope | ↑ |
| | Layoff/restructuring events, 12m (0.30) | decayed count | ↓; absolute |
| | Hiring momentum (0.25) | open roles now vs 90 days ago, % | ↑; only if a job board is configured (optional phase, not yet built) |

**Implementation note.** The Workforce pillar is scored only when a level signal (the Employee Sentiment Index)
exists. Without it the pillar is *unavailable* rather than scoring "no layoffs" as 100 - an earlier build did
that and it added up to +12 points for an absence of data. Restructuring 8-Ks are still penalised in the Events
pillar, so layoffs are never ignored.
| Events | Material-event penalty (1.00) | see below | `max(0, 100 − Σ penalties)` |

### 2.1 Event penalties

Each penalty is decayed by `exp(−age_days / 180)`.

| Event | Detection | Penalty |
|---|---|---|
| Bankruptcy filing | 8-K 1.03 / news | 100 (and the health score is capped at 10) |
| Going-concern doubt in latest 10-K/10-Q | Full-text match | 50 (and the health score is capped at 30) |
| Non-reliance on prior financials (restatement) | 8-K 4.02 | 40 |
| Delisting notice | 8-K 3.01 | 35 |
| Regulatory action / major lawsuit | News classifier | 10–25 × classifier confidence |
| CEO or CFO departure | 8-K 5.02 (role parsed) | 15 (other officers 5) |
| Auditor change | 8-K 4.01 | 15 |
| Restructuring / exit costs | 8-K 2.05 | 15 |
| Late filing notice | NT 10-K (20) / NT 10-Q (10) | 10–20 |
| Debt acceleration | 8-K 2.04 | 30 |
| Unusual statement changes | M5b anomaly percentile ≥ 0.95 | 10 |
| Material impairment | 8-K 2.06 | 15 |
| Data breach | News classifier / 8-K 1.05 | 15 |

The events pillar is penalty-only. Good news reaches the score through the news pillar.
A single real-world event (an 8-K plus 30 articles about it) is first merged into **one** event:
same type, ±7-day window. This stops one story from being counted many times.

### 2.2 Financial-sector variant (banks, SIC 6000–6399)

Altman Z, current ratio and FCF margin do not apply to banks. For banks, the Financial pillar uses these factors instead:

| Factor (weight) | Raw value | Direction |
|---|---|---|
| Equity / total assets (0.25) | × | ↑ |
| Unrealised loss on HTM + AFS securities / equity (0.25) | fair value − amortised cost, from XBRL | ↓; loss > 50% of equity → cap 15 |
| Deposit growth YoY (0.15) | % | ↑; < −10% → cap 30 |
| Loans / deposits (0.10) | × | ↓ (peer percentile) |
| Net income / assets, TTM (0.15) | % | ↑ |

The uninsured-deposit factor from the original design was dropped: it is not tagged in XBRL, so it could never
be computed and only lowered every bank's coverage. Form 25-NSE (exchange removal of a security) is
informational, not a penalty, because exchanges also file it whenever *debt* securities mature; the distress
signal is 8-K Item 3.01.

Bank percentiles use only the bank peer group. This variant is what lets the SVB case study show the
securities-loss signal that was in its public filings: as of 2022-12-31 ECHO scores SVB 47 (Watch) with
"unrealised securities losses equal 121% of equity" as the largest drag, ten weeks before the bank failed.


---

## 3. Composite score, missing data, confidence

```
pillar score     S_p = Σ_f a_f · s_f          (a_f re-normalised over available factors)
health score     H   = Σ_p w̃_p · S_p          (w̃_p = w_p re-normalised over available pillars)
coverage         c_p = Σ_{available f} a_f × freshness_p      ∈ [0, 1]
confidence       C   = Σ_p w_p · c_p           (original weights, so missing pillars lower C)
```

- `freshness_p` decays as data ages. For example, if the latest financials were filed more than 15 months ago,
  financial freshness is 0.5.
- Hard caps (bankruptcy, going concern) are applied after the weighted mean.
- If `C < 0.40`, the score is reported as **"Insufficient data"** and the available pillars are still shown.

**Bands** (provisional; the percentile construction centres a typical company near 50–60):

| Score | Band |
|---|---|
| 70–100 | Strong |
| 55–69 | Stable |
| 40–54 | Watch |
| 25–39 | Weak |
| 0–24 | Critical |

---

## 4. Explainability: exact additive attribution

Since the weights sum to 1, the health score minus a neutral 50 splits exactly into per-factor
contributions:

```
H − 50 = Σ_p Σ_f  w̃_p · a_f · (s_f − 50)          impact_f := w̃_p · a_f · (s_f − 50)
```

Each factor's `impact` is in score points, and the impacts add up to the score with nothing left over. This drives:

- the "why?" drawer: the top positive and negative impacts, each with its evidence link;
- score-change explanations, where the change between two reports is decomposed into the change in each factor's impact;
- the input to the LLM explanation layer.

A unit test asserts `|50 + Σ impacts − H| < 1e-9` for every sample company, ignoring capped cases, which are reported
separately as an "override".

For the ML distress model (§5), SHAP values (TreeExplainer) provide the matching "drivers" list.

---

## 5. ML components

Moved to [ML_PIPELINE.md §4](ML_PIPELINE.md#4-model-catalogue), which covers each model's approach, baselines, data, splits and metrics.
Every dashboard number is tagged as **ML**, **Stat** or **Rule** there.

---

## 6. Warning signals

Warning signals are deterministic rules evaluated after scoring. They are listed in the report even
when the overall score looks fine.

| Code | Rule | Severity |
|---|---|---|
| `BANKRUPTCY` | 8-K 1.03 in last 12 months | Critical |
| `GOING_CONCERN` | Going-concern language in latest 10-K/10-Q | Critical |
| `RESTATEMENT` | 8-K 4.02 in last 12 months | High |
| `ALTMAN_DISTRESS` | Z < 1.81 (Z″ < 1.1) | High |
| `LIQUIDITY_SQUEEZE` | Current ratio < 1.0 and FCF negative for 2 consecutive quarters | High |
| `EXEC_TURNOVER` | ≥ 3 director/officer-change filings (8-K 5.02) within 180 days (roles are not parsed from the filing text) | Medium |
| `AUDITOR_CHANGE` | 8-K 4.01 in last 12 months | Medium |
| `DRAWDOWN` | ≥ 30% below 52-week high | Medium |
| `SENTIMENT_SHOCK` | 7-day sentiment ≥ 2σ below its 90-day baseline (≥ 5 articles) | Medium |
| `HIRING_FREEZE` | Open roles down ≥ 50% over 60 days (≥ 20 roles at start) | Medium |
| `LAYOFFS` | Layoff/restructuring event in last 90 days | Medium |
| `MARKET_ANOMALY` | A flagged trading anomaly in the last 14 days (ML champion top 1 %, or the robust-z rule max \|z\| ≥ 5 when no ML model passed the gate) | Low |
| `STATEMENT_ANOMALY` | M5b anomaly percentile ≥ 0.95 | Medium |
| `DISTRESS_MODEL` | M7 risk band Elevated (≥ 3 %) or High (≥ 10 %) | Medium / High |
| `LATE_FILING`, `DELISTING`, `DEBT_ACCELERATION`, `CYBER_INCIDENT` | NT 10-K/Q, 8-K 3.01, 2.04, 1.05 in last 12 months | High / Medium |
| `NEGATIVE_EQUITY`, `SECURITIES_LOSSES`, `DEPOSIT_OUTFLOW` | balance-sheet rules (bank rules for SIC 6000–6399) | Medium / High |
| `SCORE_DROP` (alert only) | Health score falls by ≥ the watchlist threshold (default 10) within 30 days | per user |

---

## 7. Evaluation plan

| What | How | Reported as |
|---|---|---|
| NLP models | Held-out test sets, compared against baselines | Table of macro-F1 and per-class P/R |
| Anomaly detector | Synthetic injection (spikes, level shifts) on real series | Precision@k / recall |
| Distress model | Train ≤ 2021, validate 2022, test 2023–2025, so that no future data leaks into training | ROC-AUC, PR-AUC, Brier, calibration plot, SHAP summary |
| **Health score backtest** | Point-in-time scores at 12, 6 and 3 months before a distress event, for ~20 distressed companies (e.g. Silicon Valley Bank 2023, Bed Bath & Beyond 2023, Rite Aid 2023, WeWork 2023, Spirit Airlines 2024, Big Lots 2024) and ~40 sector/size-matched survivors | AUC of `100 − H` as a distress predictor; median lead time; per-pillar ablation |
| Weight calibration | Optional: logistic regression of the distress label on the pillar scores, with coefficients compared to the hand-set weights | Table + a decision on whether to adopt them |
| Case studies | Three or four narrated walk-throughs, including one where the score was wrong | Report chapter / viva demo |

**Backtest constraints:**

- News history is limited to about 3 months (GDELT DOC API), so backtests use the Financial, Market and Events
  pillars only, and say so.
- Delisted companies' price history may be missing from free sources. This creates survivorship bias, which must be measured and reported.
- Point-in-time discipline: a filing is usable from its `filed` date, and the peer distributions are rebuilt as of
  each backtest date.

---

## 8. Known limitations (to state in the report)

- The weights are expert-set, not learned. Calibration (§7) only partly addresses this.
- Workforce and employee-sentiment coverage is sparse, and the Kaggle review data ends around 2021, so the workforce pillar is often stale or missing and confidence drops accordingly.
- Headline-level sentiment misses nuance and sarcasm, and media attention is skewed toward large companies.
- Percentile scoring is relative: a "Strong" company in a collapsing sector is strong only relative to its peers. The absolute guard-rails mitigate this but do not remove it.
- Correlation, not causation: ECHO reports observable signals, not the causes behind them.
