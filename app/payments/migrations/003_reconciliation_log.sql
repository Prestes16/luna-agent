-- ============================================================
-- Luna Pay-Flow — Migration v3: Reconciliation Log
-- Execute no Supabase SQL Editor APOS 002_profit_engine.sql
-- ============================================================

-- Tabela de log histórico de reconciliações de tesouraria
CREATE TABLE IF NOT EXISTS reconciliation_log (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grains_in_circulation NUMERIC(18, 4) NOT NULL DEFAULT 0,
    usdc_liability       NUMERIC(18, 6) NOT NULL DEFAULT 0,
    usdc_on_chain        NUMERIC(18, 6),               -- NULL se RPC indisponível
    needs_rebalancing    BOOLEAN,
    status               TEXT NOT NULL DEFAULT 'healthy',   -- healthy | needs_rebalancing | rpc_unavailable
    wallet               TEXT,
    checked_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recon_log_checked_at ON reconciliation_log (checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_recon_log_status     ON reconciliation_log (status);

-- RLS: apenas service_role pode ler/escrever
ALTER TABLE reconciliation_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all_reconciliation_log"
    ON reconciliation_log FOR ALL TO service_role USING (true) WITH CHECK (true);

-- RPC auxiliar — últimas N reconciliações
CREATE OR REPLACE FUNCTION get_recent_reconciliations(n INT DEFAULT 50)
RETURNS SETOF reconciliation_log LANGUAGE sql AS $$
    SELECT * FROM reconciliation_log ORDER BY checked_at DESC LIMIT n;
$$;
