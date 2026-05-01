-- Migration 004: pending_credits
-- Garante que nenhum usuário perde Grains por falha transitória durante confirm-tx.
-- O retry_job varre esta tabela a cada 60s e credita qualquer pendência.

CREATE TABLE IF NOT EXISTS pending_credits (
  id            BIGSERIAL PRIMARY KEY,
  tx_signature  TEXT        NOT NULL UNIQUE,   -- anti-replay: uma entrada por tx
  user_id       TEXT        NOT NULL,           -- external_id do usuário
  grains        FLOAT       NOT NULL,           -- quantidade de Grains a creditar
  usdc_amount   FLOAT       NOT NULL,           -- valor USDC original (para registro)
  status        TEXT        NOT NULL DEFAULT 'pending',  -- pending | credited | failed
  attempts      INT         NOT NULL DEFAULT 0, -- contagem de tentativas do retry_job
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  credited_at   TIMESTAMPTZ                     -- preenchido quando status = 'credited'
);

-- Índices para performance nas queries do retry_job
CREATE INDEX IF NOT EXISTS idx_pending_credits_status
  ON pending_credits (status, attempts);

CREATE INDEX IF NOT EXISTS idx_pending_credits_user_id
  ON pending_credits (user_id);

-- RLS: apenas service role acessa (sem acesso anon)
ALTER TABLE pending_credits ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_only" ON pending_credits;
CREATE POLICY "service_only"
  ON pending_credits
  USING (auth.role() = 'service_role');

-- Comentário explicativo
COMMENT ON TABLE pending_credits IS
  'Fila de créditos pendentes. Inserido ANTES de add_grains. '
  'retry_job.py tenta creditar a cada 60s até MAX_ATTEMPTS. '
  'Garante zero perda de fundos mesmo com falha do Supabase.';
