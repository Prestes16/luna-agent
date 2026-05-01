-- ============================================================
-- Luna Pay-Flow — Migration v2: ProfitEngine
-- Execute no Supabase SQL Editor APOS 001_payflow_schema.sql
-- ============================================================

-- Novos campos em api_cost_log
ALTER TABLE api_cost_log ADD COLUMN IF NOT EXISTS model_tier      TEXT         DEFAULT 'MODEL_BASIC';
ALTER TABLE api_cost_log ADD COLUMN IF NOT EXISTS infra_fee_grains NUMERIC(18,4) DEFAULT 0;
ALTER TABLE api_cost_log ADD COLUMN IF NOT EXISTS operation        TEXT         DEFAULT 'chat';

-- Indices para analytics
CREATE INDEX IF NOT EXISTS idx_cost_log_tier      ON api_cost_log (model_tier);
CREATE INDEX IF NOT EXISTS idx_cost_log_operation ON api_cost_log (operation);

-- ─── RPCs de agregacao para o Admin Dashboard ─────────────────────────────────

CREATE OR REPLACE FUNCTION sum_usdc_received()
RETURNS NUMERIC LANGUAGE sql AS $$
    SELECT COALESCE(SUM(usdc_amount), 0) FROM payment_history WHERE status = 'finalized';
$$;

CREATE OR REPLACE FUNCTION sum_api_spend_usd()
RETURNS NUMERIC LANGUAGE sql AS $$
    SELECT COALESCE(SUM(cost_usd), 0) FROM api_cost_log;
$$;

CREATE OR REPLACE FUNCTION sum_grains_debited()
RETURNS NUMERIC LANGUAGE sql AS $$
    SELECT COALESCE(SUM(grains_debited), 0) FROM api_cost_log;
$$;

CREATE OR REPLACE FUNCTION sum_grains_credited()
RETURNS NUMERIC LANGUAGE sql AS $$
    SELECT COALESCE(SUM(grains_credited), 0) FROM payment_history WHERE status = 'finalized';
$$;

CREATE OR REPLACE FUNCTION count_active_recharges()
RETURNS BIGINT LANGUAGE sql AS $$
    SELECT COUNT(*) FROM payment_history WHERE status = 'pending';
$$;

CREATE OR REPLACE FUNCTION sum_user_balances()
RETURNS NUMERIC LANGUAGE sql AS $$
    SELECT COALESCE(SUM(balance_grains), 0) FROM users;
$$;