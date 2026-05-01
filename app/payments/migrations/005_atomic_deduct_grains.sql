-- Migration 005: Atomic deduct_grains RPC
-- Prevents race conditions when multiple simultaneous API calls deduct Grains.
-- Called by supabase_client.deduct_grains() before falling back to read+patch.

-- Atomic deduction: GREATEST(0, balance - amount) prevents negative balance.
CREATE OR REPLACE FUNCTION deduct_grains(p_external_id text, p_amount float)
RETURNS void
LANGUAGE sql
AS $$
  UPDATE users
  SET balance_grains = GREATEST(0, balance_grains - p_amount)
  WHERE external_id = p_external_id;
$$;

-- Complementary atomic add (already used via add_grains RPC, recreated here
-- to guarantee both exist together — idempotent via CREATE OR REPLACE).
CREATE OR REPLACE FUNCTION add_grains(p_external_id text, p_amount float)
RETURNS void
LANGUAGE sql
AS $$
  UPDATE users
  SET balance_grains = balance_grains + p_amount
  WHERE external_id = p_external_id;
$$;

-- Grant execute to service role (used by Supabase service key)
GRANT EXECUTE ON FUNCTION deduct_grains(text, float) TO service_role;
GRANT EXECUTE ON FUNCTION add_grains(text, float) TO service_role;
