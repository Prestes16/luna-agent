-- ============================================================
-- Luna Pay-Flow — Schema v1
-- Execute no Supabase SQL Editor
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tabela de usuarios
CREATE TABLE IF NOT EXISTS users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id      TEXT UNIQUE NOT NULL,
    balance_grains   NUMERIC(18, 4) NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_external_id ON users (external_id);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Tabela de historico de pagamentos (anti-replay)
CREATE TABLE IF NOT EXISTS payment_history (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_signature     TEXT UNIQUE,
    user_external_id TEXT NOT NULL,
    usdc_amount      NUMERIC(18, 6) NOT NULL DEFAULT 0,
    grains_credited  NUMERIC(18, 4) NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'pending',
    qr_reference     TEXT,
    expires_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_signature ON payment_history (tx_signature);
CREATE INDEX IF NOT EXISTS idx_payment_reference ON payment_history (qr_reference);
CREATE INDEX IF NOT EXISTS idx_payment_user      ON payment_history (user_external_id);
CREATE INDEX IF NOT EXISTS idx_payment_status    ON payment_history (status);

-- Tabela de log de custo de API
CREATE TABLE IF NOT EXISTS api_cost_log (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_external_id TEXT NOT NULL,
    provider         TEXT NOT NULL,
    tokens_in        INTEGER NOT NULL DEFAULT 0,
    tokens_out       INTEGER NOT NULL DEFAULT 0,
    cost_usd         NUMERIC(18, 8) NOT NULL DEFAULT 0,
    grains_debited   NUMERIC(18, 4) NOT NULL DEFAULT 0,
    markup           NUMERIC(6, 4) NOT NULL DEFAULT 2.2,
    session_id       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cost_log_user    ON api_cost_log (user_external_id);
CREATE INDEX IF NOT EXISTS idx_cost_log_provider ON api_cost_log (provider);
CREATE INDEX IF NOT EXISTS idx_cost_log_session  ON api_cost_log (session_id);

-- Row Level Security
ALTER TABLE users            ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_history  ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_cost_log     ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all_users"        ON users           FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_payments"     ON payment_history FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_api_cost_log" ON api_cost_log    FOR ALL TO service_role USING (true) WITH CHECK (true);
