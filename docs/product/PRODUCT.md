# ECHO — Product and Business Model

ECHO is a single interface for understanding the **publicly observable** health, risks and trends of a
company. It is explicitly *not* an investment-advice product: every screen and API payload separates
**observable signals** (filings, events, headlines), **model estimates** (calibrated probabilities with
stated limitations) and the fact that neither is professional financial advice.

## Who it is for

| Segment | Job to be done | What ECHO gives them |
|---|---|---|
| Retail investors and students | "Is anything wrong with this company that I should read about?" | Health score, warning signals with source links, plain-language summary |
| Equity / credit analysts | Fast first-pass screening and monitoring of a coverage list | Watchlists, score-drop alerts, peer-relative factors, PDF reports, history |
| Job seekers | "Is this employer stable?" | Workforce pillar, layoff/restructuring events, distress estimate |
| Procurement / B2B risk teams | Supplier and counterparty monitoring | Watchlists at scale, API access, alerts |
| Researchers / educators | Reproducible corporate-distress research | Point-in-time datasets, model cards, open methodology |

## Plans (implemented in `backend/.../model/Plan.java`, enforced by `PlanService`)

| | Free | Pro ($29/mo) | Enterprise ($299/mo) |
|---|---|---|---|
| Fresh analyses per day | 5 | 100 | 2,000 |
| Watchlists × companies | 1 × 5 | 10 × 50 | 100 × 500 |
| Compare at once | 2 | 4 | 8 |
| Score history | 12 months | full point-in-time | full point-in-time |
| Exports | CSV | CSV + PDF executive report | CSV + PDF |
| API keys / calls per day | — | 2 / 1,000 | 10 / 50,000 |
| Alerts | in-app | in-app | in-app (+ webhooks, roadmap) |

Cached reports are free to view for everyone (including anonymous visitors); limits apply to *fresh*
analyses, exports and API calls, which are the actions that cost compute and data-provider quota.
Billing runs in `demo` mode (instant activation, no payment); production plugs a payment provider
(e.g. Stripe Checkout + webhook) into `AccountService.checkout`.

## Unit economics (assumptions to validate)

- Marginal cost per fresh analysis: ~2 s of CPU in demo mode; live mode is dominated by rate-limited free
  data sources, so caching (Redis, 24 h report TTL) is the main cost lever.
- The optional LLM narrative is one call per *report*, cached with the report — page views never call the LLM.
- Paid data (licensed reviews, real-time prices) would be the largest variable cost in a commercial
  deployment and is the main reason for the Pro/Enterprise price gap.

## Commercial roadmap

1. **Licensed data**: a commercial employee-review source and an exchange-licensed price feed behind the
   existing `ReviewSource` / `PriceSource` interfaces (the Kaggle dataset is academic-use only).
2. **India (NSE/BSE)**: one `MarketProvider` plus Ind-AS and SEBI LODR mapping files (DATA_STRATEGY §2).
3. **Teams**: organisations, shared watchlists, SSO (SAML/OIDC), audit log.
4. **Alert channels**: email digests, Slack/Teams webhooks, signed webhooks for the API.
5. **Portfolio view**: aggregate health and concentration of a list of holdings or suppliers.
6. **Premium AI reports**: LLM-written long-form reports, still grounded by the validator, with citations.
7. **Event-study backtests** exposed as a research product (point-in-time data is already in place).

## Responsible-use guardrails (built in)

- Disclaimer on every report, PDF and API payload; no buy/sell language (enforced in the LLM grounding check).
- Historical case studies are labelled as such and analysed only with data filed before the event.
- Missing data lowers the shown confidence and is never filled with defaults; below 40 % coverage no score is shown.
- No scraping of sites whose terms forbid it; only headline metadata is stored, never article bodies.
