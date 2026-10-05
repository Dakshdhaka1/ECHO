# ECHO — Data Strategy

Status: **implemented** (2026-10-05). Implementation notes are marked *Implementation*. Companion to [ARCHITECTURE.md](ARCHITECTURE.md),
[ML_PIPELINE.md](ML_PIPELINE.md) and [SCORING.md](SCORING.md).

Rules that override everything below:

1. **Legitimate sources only.** ECHO uses documented APIs, bulk downloads and published datasets. It
   does no scraping of sites whose terms forbid it (Glassdoor, LinkedIn, Indeed, paywalled news).
2. **No fabricated data.** Demo mode replays real data that was recorded from real sources
   (§6). Synthetic data appears only in tests and in the anomaly-injection benchmark, and is labelled
   there.
3. **Point-in-time.** A fact is usable only from its publication/`filed` date (§5).
4. **Historical analysis, not certainty.** Case studies show which public signals were visible
   *before* an event. ECHO does not claim it predicts bankruptcy with certainty, and every report
   carries that disclaimer.

---

## 1. Sources by signal

| Signal | Phase-1 source (US) | Access | Licence / terms | Stored in repo? |
|---|---|---|---|---|
| Identity, tickers, former names, SIC | SEC `company_tickers.json`, EDGAR submissions API | Free, no key; `User-Agent` with contact, ≤10 req/s | US government data, public domain | Yes (demo snapshot) |
| Financial statements | SEC XBRL `companyfacts` API; `companyfacts.zip` bulk for the training universe | Free, no key | Public domain | Demo companies: yes. Bulk: no (download script) |
| Material events | EDGAR submissions → 8-K item codes | Free, no key | Public domain | Yes |
| Going-concern language | EDGAR full-text search | Free, no key | Public domain | Derived flag only |
| Prices / volume | Pluggable `PriceSource`: local CSV (`data/raw/prices/`) or Alpha Vantage (free key) | Free tier | **Verify each provider's redistribution terms before committing any price file.** Until they are verified, price snapshots stay in git-ignored `data/raw/` and are re-recorded locally. | No (L1 open) |
| News headlines | GDELT DOC 2.0 API | Free, no key | GDELT allows unrestricted use with citation. Only headline, URL, outlet and timestamp are stored, never article bodies. | Yes (metadata only) |
| Employee reviews | Kaggle "Glassdoor Job Reviews" dataset, through the `ReviewSource` interface | Free Kaggle account | **Verify the dataset licence (L2).** It is used for academic training and demonstration. A commercial deployment needs a licensed source, which plugs in through the same interface. | No. A download script plus the trained model's aggregates only |
| Sentiment training text | `zeroshot/twitter-financial-news-sentiment` (Hugging Face) | Free | MIT (L3 resolved: dataset card, 2026-10-05) | No (downloaded) |
| Sentiment evaluation text | Financial PhraseBank | Free | CC BY-NC-SA 3.0: **non-commercial**, so evaluation only (see ML_PIPELINE §3) | No |
| Hiring activity (optional) | Greenhouse / Lever public job-board APIs | Free, no key | Public APIs | Later phase |

Explicitly excluded: Glassdoor/LinkedIn/Indeed scraping, full article text, social-media scraping, and
Yahoo Finance scraping libraries (their terms forbid it).

*Implementation findings (2026-10-05):*
- **Stooq** now answers CSV downloads with a JavaScript browser challenge, so it cannot be used programmatically
  and was dropped. Prices come from Alpha Vantage (free key) or user-supplied CSVs. With no prices, the Market pillar
  is shown as unavailable - prices are never simulated. Alpha Vantage's public `demo` key serves IBM only; that
  series (recorded locally) is the training/evaluation data of the market anomaly model.
- **Alpha Vantage free tier (tested 2026-10-05):** `TIME_SERIES_DAILY` with `outputsize=full` is premium; the free
  tier returns the latest 100 trading days. `TIME_SERIES_WEEKLY_ADJUSTED` returns full split- and dividend-adjusted
  history (1999 onward). ECHO therefore computes returns, drawdown and sector-ETF excess returns from weekly data
  and uses daily data for volume, recent volatility and daily anomalies. Recording the demo universe costs about
  21 of the 25 daily requests. Delisted tickers (BBBY, SIVB, WE) are not served, so those case studies have no
  Market pillar.
- **GDELT** throttles far below its documented "one request per 5 s": responses take 10–15 s and requests spaced
  5–10 s after the previous response still get HTTP 429. The client therefore waits 30 s after each response,
  backs off 45 s on 429, and keeps whatever windows succeeded. Recording a 90-day news snapshot takes minutes per
  company; companies whose recording did not complete show the News pillar as unavailable.
- **SEC** accepted a generic project User-Agent; set `SEC_USER_AGENT` to your own contact in live use.
- A few XBRL facts carry typo'd dates (e.g. year 0201), which overflow nanosecond timestamps; facts outside
  1990–2100 are dropped at extraction.

### Licence checklist (must be resolved before the related phase)

| # | Item | Blocks |
|---|---|---|
| L1 | Price provider redistribution terms | Committing price snapshots to `data/sample/` |
| L2 | Kaggle Glassdoor dataset licence — **checked 2026-10-05: Kaggle lists no licence**, so academic use only; never committed or redistributed | Phase 6 (employee reviews) |
| L3 | twitter-financial-news-sentiment licence - **resolved: MIT** | Phase 5 (sentiment training) |
| L4 | Model licences (FinBERT, DistilRoBERTa, MiniLM) recorded in each model card | Phase 5 |

---

## 2. Market-agnostic provider layer (US now, India later)

Everything **market-specific** sits behind one `MarketProvider`. Everything else in ECHO works on
canonical schemas and never sees SEC-specific concepts.

```python
class MarketProvider(Protocol):
    market: str                                        # "US_SEC" now; "IN_NSE", "IN_BSE" later
    def resolve(self, query: str) -> list[CompanyCandidate]: ...
    def financial_facts(self, company: CompanyRef) -> list[CanonicalFact]: ...      # with filed dates
    def disclosures(self, company: CompanyRef, since: date) -> list[CanonicalEvent]: ...
    def price_source(self) -> PriceSource: ...

class ReviewSource(Protocol):                          # market-independent signal sources
    def reviews(self, company: CompanyRef, since: date) -> list[Review]: ...
class NewsSource(Protocol):
    def articles(self, company: CompanyRef, since: date) -> list[Article]: ...
```

The **canonical schemas** are what make a new market a plug-in rather than a rewrite:

- **`CanonicalFact`**: `(company, item, period_start, period_end, fiscal_period, value, unit, filed, source_ref)`.
  `item` comes from ECHO's canonical line-item list (Revenue, NetIncome, TotalAssets,
  CurrentAssets, CurrentLiabilities, TotalLiabilities, StockholdersEquity, RetainedEarnings, EBIT,
  OperatingCashFlow, CapEx, InterestExpense, Cash, LongTermDebt, SharesOutstanding,
  and bank items such as Deposits, Loans, HTM securities at cost and at fair value). Each market has a mapping file:
  `mappings/us_gaap.yaml` maps one or more US-GAAP XBRL tags, in priority order, to each item.
  `mappings/ind_as.yaml` will do the same for Indian Ind-AS XBRL later.
- **`CanonicalEvent`**: ECHO's event taxonomy (BANKRUPTCY, GOING_CONCERN, RESTATEMENT, DELISTING_NOTICE,
  AUDITOR_CHANGE, EXEC_DEPARTURE, RESTRUCTURING, IMPAIRMENT, CYBER_INCIDENT, M_AND_A, …).
  `mappings/sec_8k_items.yaml` maps 8-K item codes to it. The Indian mapping would use SEBI LODR
  Regulation 30 disclosure categories.
- **Industry**: an internal sector list, mapped from SIC for the US and from NSE industry classes later.

Adding NSE/BSE therefore means writing one `MarketProvider` plus three mapping files. Scoring, models,
backend and UI do not change. Indian sources still need to be evaluated, for example exchange
corporate-announcement feeds and XBRL financial results. Their terms are not assessed here.

---

## 3. Demo universe

Twelve companies, chosen to cover the score range. All CIKs were verified against EDGAR on 2026-10-05.

| Role | Company | CIK | Analysis date(s) | Why it is included |
|---|---|---|---|---|
| Healthy | Apple | 320193 | latest | Large, profitable reference |
| Healthy | Microsoft | 789019 | latest | |
| Healthy | NVIDIA | 1045810 | latest | High growth, high volatility |
| Healthy | Alphabet | 1652044 | latest | |
| Healthy | Amazon | 1018724 | latest | Retail sector peer for Bed Bath & Beyond |
| Healthy | Meta Platforms | 1326801 | latest + as of 2022-12-31 | Its own 2022 layoffs/drawdown is a "mixed" period |
| Mixed / risky | Tesla | 1318605 | latest | Volatility, sentiment swings, executive news |
| Mixed / risky | Intel | 50863 | latest | Deteriorating margins, restructuring (8-K 2.05) |
| Mixed / risky | Boeing | 12927 | latest | Negative equity, regulatory events |
| Historical distress | Bed Bath & Beyond (now "20230930-DK-Butterfly-1, Inc.") | 886158 | as of 2022-04, 2022-10, 2023-01 | Going-concern doubt (Jan 2023), Chapter 11 (Apr 2023) |
| Historical distress | SVB Financial Group | 719739 | as of 2022-03, 2022-09, 2022-12 | Bank failure (Mar 2023). Uses the bank variant of the financial pillar (SCORING §2.2). |
| Historical distress (optional) | WeWork | 1813756 | as of 2022-11, 2023-05 | Going concern (Aug 2023), Chapter 11 (Nov 2023) |

Historical companies are analysed **as of dates before the event**, using only data filed by then. The UI
labels them "Historical case study — as of <date>".

### What can actually be observed for each group

| Pillar | Current companies | Historical case studies |
|---|---|---|
| Financial | ✅ XBRL | ✅ XBRL, point-in-time by `filed` date |
| Events & governance | ✅ 8-K | ✅ 8-K (complete history) |
| Market | ✅ if the price source covers the ticker | ⚠️ Delisted tickers may be missing from free sources. If missing, the pillar is marked unavailable and confidence drops. |
| News sentiment | ✅ last ~3 months (GDELT DOC API window) | ❌ by default. A GDELT raw-file backfill for case-study windows is optional (Phase 5+). |
| Workforce / employee | ⚠️ The Kaggle dataset ends around 2021, so the data is shown as stale and down-weighted by freshness | ✅/⚠️ Depends on the dataset's coverage of the company |

This table goes into the report and the UI ("Data coverage" panel). Missing pillars are shown as missing and are
never filled with defaults.

---

## 4. Storage layout

```
data/
  sample/                       committed; real recorded data for the demo universe (demo mode reads only this)
    universe.yaml               demo companies, roles, as-of dates
    sec/{cik}/submissions.json.gz   raw EDGAR responses, gzipped (public domain)
    sec/{cik}/companyfacts.json.gz
    news/{cik}.jsonl            GDELT headline metadata
    reference/peer_stats_{as_of}.parquet   sector percentile tables built from the full universe
    MANIFEST.json               file → sha256, source URL, retrieved_at
  raw/                          git-ignored; bulk downloads (companyfacts.zip, Kaggle, HF datasets)
  processed/                    git-ignored; parquet outputs of the pipelines
    facts/                      canonical facts, partitioned by year of `filed`
    features/                   point-in-time feature tables
    labels/                     distress labels, review labels
```

The runtime database (PostgreSQL) holds **users, reports, history and watchlists only**. Data for
training and analysis lives in versioned files, which keeps the ML pipeline reproducible without a
database dump.

---

## 5. Point-in-time rules

- A financial fact's timestamp is its XBRL `filed` date. Period-end dates are never used for this.
- If a value is restated, the analysis uses the version that was latest **as of** the analysis date.
- TTM values are built from the latest four quarterly values known as of that date. Q4 is derived as FY − (Q1+Q2+Q3) when it is not reported separately.
- Peer percentile tables are rebuilt for every as-of date that is used, from facts known by then.
- An event counts from its filing or publication timestamp.
- Every pipeline output records `as_of`, and a unit test asserts that no input row has `filed > as_of`.

---

## 6. Demo mode = recorded real data

`DEMO_MODE=true` makes every provider read from `data/sample/` instead of the network. The snapshot is
produced by the same live adapters in **record mode**:

```
python -m pipelines.ingestion.record_sample --universe data/sample/universe.yaml
```

This writes the raw responses and `MANIFEST.json` (hash, URL, retrieval time). The demo is therefore
reproducible offline, and every number in it traces to a real public source. Re-recording updates
the snapshot. Reports show the snapshot's retrieval date as `data_as_of`.
