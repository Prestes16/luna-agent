"""
Luna Pay-Flow — PaymentService
Gerencia sessoes de pagamento USDC/Solana e processa webhooks da Helius.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.payments import supabase_client as db

logger = logging.getLogger("luna.payments.service")

# ─── Configuracao ─────────────────────────────────────────────────────────────

RECEIVER_WALLET  = os.getenv("LUNA_RECEIVER_WALLET", "HfcPmtJEMABWtrZmURT3n7EmhQUHCX6hs6Vf51uoNpdL")
USDC_MINT        = os.getenv("USDC_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
GRAINS_PER_USDC  = float(os.getenv("GRAINS_PER_USDC", "1000"))
WEBHOOK_SECRET   = os.getenv("HELIUS_WEBHOOK_SECRET", "")
QR_TIMEOUT_MIN   = 15


# ─── Excecoes ─────────────────────────────────────────────────────────────────

class PaymentError(Exception):
    pass


class ReplayAttackError(PaymentError):
    pass


class InvalidMintError(PaymentError):
    pass


class WebhookAuthError(PaymentError):
    pass


# ─── Servico de Pagamento ─────────────────────────────────────────────────────

class PaymentService:

    # ── Criar sessao de pagamento ──────────────────────────────────────────────

    def create_payment_session(
        self,
        user_id: str,
        usdc_amount: float,
    ) -> dict[str, Any]:
        """
        Cria uma sessao de pagamento:
        - Garante que o usuario existe no Supabase
        - Gera um reference UUID unico
        - Persiste no payment_history com expires_at = now + 15min
        - Retorna a URL Solana Pay e o reference para o QR

        Retorno:
            {
                "reference": "uuid",
                "solana_pay_url": "solana:...",
                "expires_at": "ISO timestamp",
                "usdc_amount": 5.0,
                "grains": 5000.0,
            }
        """
        if usdc_amount <= 0:
            raise PaymentError("Valor USDC deve ser maior que zero")

        db.upsert_user(user_id)

        reference  = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=QR_TIMEOUT_MIN)
        grains     = usdc_amount * GRAINS_PER_USDC

        # Monta URL Solana Pay (SPL Token — USDC)
        # spl-token especifica que e transferencia de token, nao SOL nativo
        params = urllib.parse.urlencode({
            "amount":    f"{usdc_amount:.6f}",
            "spl-token": USDC_MINT,
            "reference": reference,
            "label":     "Luna Grains",
            "message":   f"Compra de {grains:.0f} Luna Grains",
            "memo":      reference,
        })
        solana_pay_url = f"solana:{RECEIVER_WALLET}?{params}"

        db.record_payment(
            user_external_id = user_id,
            tx_signature     = None,
            usdc_amount      = usdc_amount,
            grains_credited  = grains,
            status           = "pending",
            qr_reference     = reference,
            expires_at       = expires_at.isoformat(),
        )

        logger.info(f"Sessao de pagamento criada | user={user_id} | ref={reference} | usdc={usdc_amount}")

        return {
            "reference":      reference,
            "solana_pay_url": solana_pay_url,
            "expires_at":     expires_at.isoformat(),
            "usdc_amount":    usdc_amount,
            "grains":         grains,
        }

    # ── Verificar assinatura do webhook Helius ─────────────────────────────────

    def verify_webhook_signature(self, raw_body: bytes, auth_header: str) -> None:
        """
        Valida o header helius-auth-token contra HELIUS_WEBHOOK_SECRET.
        Se WEBHOOK_SECRET nao estiver configurado, pula a validacao (dev mode).
        """
        if not WEBHOOK_SECRET:
            logger.warning("HELIUS_WEBHOOK_SECRET nao configurado — validacao ignorada (dev mode)")
            return

        expected = hmac.new(
            WEBHOOK_SECRET.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(auth_header or "", expected):
            raise WebhookAuthError("Assinatura do webhook invalida")

    # ── Processar webhook da Helius ────────────────────────────────────────────

    def process_webhook(self, payload: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        """
        Ponto de entrada do webhook Helius.
        O payload pode ser uma lista de transacoes ou um objeto unico.

        Fluxo:
        1. Anti-replay: verifica tx_signature
        2. Valida mint USDC
        3. Valida owner (destinatario = RECEIVER_WALLET)
        4. Confirma status finalized
        5. Busca sessao pelo reference/memo
        6. Verifica timeout (15min)
        7. Credita Grains e atualiza status
        """
        # Helius pode enviar lista ou objeto unico
        events = payload if isinstance(payload, list) else [payload]
        results = []

        for event in events:
            try:
                result = self._process_single_event(event)
                results.append(result)
            except ReplayAttackError as e:
                logger.info(f"Replay ignorado: {e}")
                results.append({"status": "ignored", "reason": "replay"})
            except InvalidMintError as e:
                logger.warning(f"Mint invalido: {e}")
                results.append({"status": "rejected", "reason": "invalid_mint"})
            except Exception as e:
                logger.error(f"Erro ao processar evento: {e}")
                results.append({"status": "error", "reason": str(e)})

        return {"processed": len(results), "results": results}

    def _process_single_event(self, event: dict[str, Any]) -> dict[str, Any]:
        signature   = event.get("signature", "")
        tx_status   = event.get("type", "")     # Helius: "TRANSFER", etc.

        # 1. Anti-replay
        if signature and db.is_signature_known(signature):
            raise ReplayAttackError(f"Assinatura ja processada: {signature}")

        # 2. Extrair transferencia de token
        usdc_amount, recipient, reference = self._extract_usdc_transfer(event)

        # 3. Valida destinatario
        if recipient.lower() != RECEIVER_WALLET.lower():
            raise PaymentError(f"Destinatario incorreto: {recipient}")

        # 4. Busca sessao pelo reference (memo)
        session = db.get_payment_by_reference(reference) if reference else None

        if not session:
            logger.warning(f"Sessao nao encontrada para reference={reference}")
            # Registra mesmo sem sessao conhecida (pode ser pagamento direto)
            db.record_payment(
                user_external_id = "unknown",
                tx_signature     = signature,
                usdc_amount      = usdc_amount,
                grains_credited  = 0,
                status           = "pending_approval",
                qr_reference     = reference,
            )
            return {"status": "pending_approval", "reason": "session_not_found", "signature": signature}

        user_id    = session["user_external_id"]
        expires_at = session.get("expires_at")

        # 5. Verifica timeout
        if expires_at:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt:
                db.update_payment_status(reference, "pending_approval", tx_signature=signature)
                logger.warning(f"Pagamento expirado | ref={reference} | user={user_id}")
                return {"status": "pending_approval", "reason": "expired", "reference": reference}

        # 6. Creditar Grains
        grains = usdc_amount * GRAINS_PER_USDC
        db.upsert_user(user_id)
        db.add_grains(user_id, grains)
        db.update_payment_status(reference, "finalized", tx_signature=signature, grains_credited=grains)

        logger.info(f"Pagamento finalizado | user={user_id} | usdc={usdc_amount} | grains={grains} | sig={signature[:16]}...")

        return {
            "status":    "finalized",
            "user_id":   user_id,
            "usdc":      usdc_amount,
            "grains":    grains,
            "reference": reference,
            "signature": signature,
        }

    def _extract_usdc_transfer(self, event: dict[str, Any]) -> tuple[float, str, str]:
        """
        Extrai valor USDC, destinatario e reference (memo) do payload Helius.
        Suporta formato Enhanced Transactions da Helius API.
        """
        # Formato Helius Enhanced Transaction
        # Uma tx pode ter múltiplas transferências de token (ex: fee refund + USDC).
        # Iteramos todas e pegamos a primeira que seja USDC — as demais são ignoradas.
        token_transfers = event.get("tokenTransfers", [])
        non_usdc_mints: list[str] = []
        for transfer in token_transfers:
            mint = transfer.get("mint", "")
            if mint != USDC_MINT:
                non_usdc_mints.append(mint)
                continue   # pula tokens que não são USDC

            raw_amount  = float(transfer.get("tokenAmount", 0))
            destination = transfer.get("toUserAccount", "")
            # USDC tem 6 decimais — Helius ja retorna em unidades humanas em tokenAmount
            return raw_amount, destination, self._extract_reference(event)

        # Havia transferências de token mas nenhuma era USDC
        if non_usdc_mints:
            raise InvalidMintError(
                f"Nenhuma transferencia USDC encontrada — mints presentes: {non_usdc_mints[:3]}"
            )

        # Fallback: accountData com tokenBalanceChanges
        # Same skip-non-USDC logic: continue past other tokens, return first USDC found.
        account_data = event.get("accountData", [])
        non_usdc_fallback: list[str] = []
        for account in account_data:
            for change in account.get("tokenBalanceChanges", []):
                if change.get("mint") != USDC_MINT:
                    non_usdc_fallback.append(change.get("mint", "?"))
                    continue
                raw_change = float(change.get("rawTokenAmount", {}).get("tokenAmount", 0))
                decimals   = int(change.get("rawTokenAmount", {}).get("decimals", 6))
                amount     = raw_change / (10 ** decimals)
                owner      = change.get("userAccount", "")
                return amount, owner, self._extract_reference(event)
        if non_usdc_fallback:
            raise InvalidMintError(
                f"Nenhuma transferencia USDC no accountData — mints: {non_usdc_fallback[:3]}"
            )

        raise PaymentError("Nenhuma transferencia USDC encontrada no payload")

    def _extract_reference(self, event: dict[str, Any]) -> str:
        """Extrai reference/memo do evento (campo memo ou instructions)."""
        # Campo memo direto
        if event.get("memo"):
            return str(event["memo"]).strip()

        # Instructions com parsed data
        instructions = event.get("instructions", [])
        for ix in instructions:
            parsed = ix.get("parsed", {})
            if isinstance(parsed, dict) and parsed.get("type") == "memo":
                return str(parsed.get("info", "")).strip()

        return ""

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_balance(self, user_id: str) -> float:
        return db.get_user_balance(user_id)

    def get_payment_status(self, reference: str) -> dict[str, Any]:
        session = db.get_payment_by_reference(reference)
        if not session:
            return {"status": "not_found"}

        # Verifica timeout em tempo real
        if session["status"] == "pending":
            expires_at = session.get("expires_at")
            if expires_at:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp_dt:
                    db.update_payment_status(reference, "expired")
                    session["status"] = "expired"

        return {
            "status":         session["status"],
            "usdc_amount":    session.get("usdc_amount", 0),
            "grains_credited": session.get("grains_credited", 0),
            "expires_at":     session.get("expires_at"),
        }

    def get_payment_history(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return db.get_payment_history(user_id, limit=limit)


# ─── Singleton ────────────────────────────────────────────────────────────────

_service: PaymentService | None = None


def get_payment_service() -> PaymentService:
    global _service
    if _service is None:
        _service = PaymentService()
    return _service
