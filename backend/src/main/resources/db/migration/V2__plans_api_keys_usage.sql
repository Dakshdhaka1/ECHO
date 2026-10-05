-- SaaS layer: subscription plans, personal API keys and usage metering (docs/product/PRODUCT.md).

ALTER TABLE users
    ADD COLUMN plan            VARCHAR(16) NOT NULL DEFAULT 'FREE' CHECK (plan IN ('FREE', 'PRO', 'ENTERPRISE')),
    ADD COLUMN plan_updated_at TIMESTAMPTZ;

-- API keys are shown once at creation; only a SHA-256 hash is stored.
CREATE TABLE api_keys (
    id           BIGSERIAL    PRIMARY KEY,
    user_id      BIGINT       NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name         VARCHAR(100) NOT NULL,
    key_prefix   VARCHAR(16)  NOT NULL,
    key_hash     CHAR(64)     NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ
);
CREATE INDEX idx_api_keys_user ON api_keys (user_id);

-- One row per metered action (analysis requests, exports, API calls); drives plan limits and the usage panel.
CREATE TABLE usage_events (
    id         BIGSERIAL   PRIMARY KEY,
    user_id    BIGINT      REFERENCES users (id) ON DELETE CASCADE,
    kind       VARCHAR(32) NOT NULL,
    company_id BIGINT      REFERENCES companies (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_usage_events_user_kind_time ON usage_events (user_id, kind, created_at DESC);
