"""
Luna Pay-Flow — Retry Job para pending_credits
Roda em background (asyncio.create_task) a cada 60 segundos.
Garante que nenhum usuário perca Grains por falha transitória de rede/Supabase.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("luna.payments.retry_job")

MAX_ATTEMPTS = 10          # após 10 tentativas, desiste e loga alerta crítico
RETRY_INTERVAL_SECS = 60  # intervalo entre varreduras


async def run_retry_loop() -> None:
    """Loop assíncrono — chamado via asyncio.create_task() no startup do FastAPI."""
    logger.info("[RetryJob] Iniciado — varredura a cada %ds", RETRY_INTERVAL_SECS)
    while True:
        try:
            await _process_pending()
        except Exception as e:
            logger.error("[RetryJob] Erro inesperado na varredura: %s", e)
        await asyncio.sleep(RETRY_INTERVAL_SECS)


async def _process_pending() -> None:
    """Processa todos os pending_credits com status='pending' e attempts < MAX_ATTEMPTS."""
    from app.payments import supabase_client as db

    rows = db.get_pending_credits_to_retry(max_attempts=MAX_ATTEMPTS)
    if not rows:
        return

    logger.info("[RetryJob] %d crédito(s) pendente(s) encontrado(s)", len(rows))

    for row in rows:
        tx_sig     = row["tx_signature"]
        user_id    = row["user_id"]
        grains     = float(row["grains"])
        usdc       = float(row.get("usdc_amount", 0))
        attempts   = int(row.get("attempts", 0))

        logger.info(
            "[RetryJob] Tentando creditar tx=%s... user=%s grains=%.0f tentativa=%d",
            tx_sig[:20], user_id, grains, attempts + 1,
        )

        # Garante que o usuário existe antes de creditar
        db.upsert_user(user_id)

        ok = db.add_grains(user_id, grains)
        if ok:
            # Crédito bem-sucedido: marca como done + grava no historico definitivo
            db.mark_pending_credit_done(tx_sig)
            db.record_payment(
                user_external_id = user_id,
                tx_signature     = tx_sig,
                usdc_amount      = usdc,
                grains_credited  = grains,
                status           = "finalized",
            )
            logger.info(
                "[RetryJob] ✅ Crédito OK | tx=%s... | user=%s | grains=%.0f",
                tx_sig[:20], user_id, grains,
            )
        else:
            db.increment_pending_credit_attempts(tx_sig)
            new_attempts = attempts + 1
            if new_attempts >= MAX_ATTEMPTS:
                # Alerta crítico: crédito travado — requer intervenção manual
                logger.critical(
                    "[RetryJob] ❌ ATENÇÃO: crédito travado após %d tentativas! "
                    "tx=%s user=%s grains=%.0f — verificar Supabase manualmente",
                    new_attempts, tx_sig, user_id, grains,
                )
            else:
                logger.warning(
                    "[RetryJob] ⚠ add_grains falhou (tentativa %d/%d) | tx=%s...",
                    new_attempts, MAX_ATTEMPTS, tx_sig[:20],
                )
