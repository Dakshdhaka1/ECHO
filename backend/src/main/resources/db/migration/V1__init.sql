-- ECHO core schema. See docs/architecture/ARCHITECTURE.md §6.
-- Training data, features and model artifacts are NOT stored here (see DATA_STRATEGY.md §4).

CREATE TABLE users (
    id            BIGSERIAL    PRIMARY KEY,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(100) NOT NULL,
    display_name  VARCHAR(100),
    role          VARCHAR(16)  NOT NULL DEFAULT 'USER' CHECK (role IN ('USER', 'ADMIN')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Market-agnostic company registry. market_id is the market's canonical id (CIK for US_SEC).
CREATE TABLE companies (
    id              BIGSERIAL    PRIMARY KEY,
    market          VARCHAR(16)  NOT NULL,
    market_id       VARCHAR(32)  NOT NULL,
    name            VARCHAR(255) NOT NULL,
    ticker          VARCHAR(16),
    exchange        VARCHAR(32),
    country         CHAR(2),
    industry_scheme VARCHAR(8),
    industry_code   VARCHAR(16),
    sector          VARCHAR(64),
    status          VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE', 'DELISTED', 'BANKRUPT', 'ACQUIRED', 'UNKNOWN')),
    is_demo         BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (market, market_id)
);
CREATE INDEX idx_companies_ticker ON companies (upper(ticker));

-- Tickers are reused and names change, so identifiers carry validity dates.
CREATE TABLE company_identifiers (
    id         BIGSERIAL    PRIMARY KEY,
    company_id BIGINT       NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    scheme     VARCHAR(16)  NOT NULL
               CHECK (scheme IN ('CIK', 'TICKER', 'ISIN', 'LEI', 'NSE_SYMBOL', 'BSE_CODE', 'FORMER_NAME')),
    value      VARCHAR(255) NOT NULL,
    valid_from DATE,
    valid_to   DATE,
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);
CREATE UNIQUE INDEX uq_company_identifiers
    ON company_identifiers (company_id, scheme, value, COALESCE(valid_from, DATE '0001-01-01'));
CREATE INDEX idx_company_identifiers_lookup ON company_identifiers (scheme, upper(value));

CREATE TABLE analysis_jobs (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   BIGINT      NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    as_of        DATE        NOT NULL,
    status       VARCHAR(16) NOT NULL DEFAULT 'QUEUED'
                 CHECK (status IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED')),
    requested_by BIGINT      REFERENCES users (id) ON DELETE SET NULL,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ
);
-- At most one active job per company and as-of date.
CREATE UNIQUE INDEX uq_analysis_jobs_active
    ON analysis_jobs (company_id, as_of) WHERE status IN ('QUEUED', 'RUNNING');

-- Append-only report snapshots; payload is the full AnalysisResult.
CREATE TABLE reports (
    id                    BIGSERIAL    PRIMARY KEY,
    company_id            BIGINT       NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    job_id                UUID         REFERENCES analysis_jobs (id) ON DELETE SET NULL,
    as_of                 DATE         NOT NULL,
    generated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_case_study         BOOLEAN      NOT NULL DEFAULT FALSE,
    health_score          SMALLINT     CHECK (health_score BETWEEN 0 AND 100),
    band                  VARCHAR(24),
    confidence            NUMERIC(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    distress_prob         NUMERIC(5, 4) CHECK (distress_prob BETWEEN 0 AND 1),
    schema_version        VARCHAR(16)  NOT NULL,
    model_version         VARCHAR(64)  NOT NULL,
    explanation_generator VARCHAR(16)  NOT NULL,
    payload               JSONB        NOT NULL
);
CREATE INDEX idx_reports_company_latest ON reports (company_id, as_of DESC, generated_at DESC);

CREATE TABLE score_points (
    company_id   BIGINT        NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    as_of        DATE          NOT NULL,
    health_score SMALLINT      CHECK (health_score BETWEEN 0 AND 100),
    confidence   NUMERIC(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    pillars      JSONB         NOT NULL,
    source       VARCHAR(16)   NOT NULL CHECK (source IN ('LIVE', 'BACKFILL')),
    report_id    BIGINT        REFERENCES reports (id) ON DELETE SET NULL,
    PRIMARY KEY (company_id, as_of)
);

CREATE TABLE watchlists (
    id         BIGSERIAL    PRIMARY KEY,
    user_id    BIGINT       NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name       VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

CREATE TABLE watchlist_items (
    watchlist_id         BIGINT      NOT NULL REFERENCES watchlists (id) ON DELETE CASCADE,
    company_id           BIGINT      NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    score_drop_threshold SMALLINT    NOT NULL DEFAULT 10 CHECK (score_drop_threshold BETWEEN 1 AND 100),
    added_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (watchlist_id, company_id)
);

CREATE TABLE alerts (
    id         BIGSERIAL    PRIMARY KEY,
    user_id    BIGINT       NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    company_id BIGINT       NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    report_id  BIGINT       REFERENCES reports (id) ON DELETE SET NULL,
    type       VARCHAR(32)  NOT NULL,
    severity   VARCHAR(16)  NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    message    VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    read_at    TIMESTAMPTZ
);
CREATE INDEX idx_alerts_user_unread ON alerts (user_id, created_at DESC) WHERE read_at IS NULL;
