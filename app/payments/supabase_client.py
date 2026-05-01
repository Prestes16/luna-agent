"""
Luna Pay-Flow — Supabase Client
Wrapper leve usando httpx para a Supabase REST API (sem SDK pesado).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("luna.payments.supabase")

# Lê as vars em runtime (não no import) para capturar load_dotenv() do main.py
def _get_url() -> str:
    return os.getenv("SUPABASE_URL", "").rstrip("/")

def _get_key() -> str:
    return os.getenv("SUPABASE_SERVICE_KEY", "")


def _headers() -> dict[str, str]:
    key = _get_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _url(table: str) -> str:
    return f"{_get_url()}/rest/v1/{table}"


def _check_config() -> bool:
    url, key = _get_url(), _get_key()
    if not url or not key:
        logger.warning("Supabase nao configurado (SUPABASE_URL / SUPABASE_SERVICE_KEY ausentes)")
        return False
    return True


# ─── Usuarios ────────────────────────────────────────────────────────────────

def upsert_user(external_id: str) -> dict[str, Any] | None:
    """Cria ou retorna usuario pelo external_id."""
    if not _check_config():
        return None
    try:
        # Tenta inserir — se já existe (409) faz GET para retornar o existente
        resp = httpx.post(
            _url("users"),
            headers={**_headers(), "Prefer": "resolution=ignore-duplicates,return=representation"},
            json={"external_id": external_id, "balance_grains": 0},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return data[0] if data else None
        # 409 ou outro — busca o existente
        r2 = httpx.get(
            _url("users"),
            headers=_headers(),
            params={"external_id": f"eq.{external_id}", "select": "id,external_id,balance_grains"},
            timeout=10,
        )
        r2.raise_for_status()
        data = r2.json()
        return data[0] if data else None
    except Exception as e:
        logger.error(f"upsert_user erro: {e}")
        return None


def get_user_balance(external_id: str) -> float:
    """Retorna o saldo em Grains do usuario."""
    if not _check_config():
        return 0.0
    try:
        resp = httpx.get(
            _url("users"),
            headers=_headers(),
            params={"external_id": f"eq.{external_id}", "select": "balance_grains"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[0].get("balance_grains", 0))
    except Exception as e:
        logger.error(f"get_user_balance erro: {e}")
    return 0.0


def add_grains(external_id: str, grains: float) -> bool:
    """Incrementa o saldo de Grains do usuario atomicamente via RPC."""
    if not _check_config():
        return False
    try:
        # Usa RPC para incremento atomico (evita race condition)
        resp = httpx.post(
            f"{_get_url()}/rest/v1/rpc/add_grains",
            headers=_headers(),
            json={"p_external_id": external_id, "p_amount": grains},
            timeout=10,
        )
        if resp.status_code == 404:
            # RPC nao existe ainda — fallback manual (menos seguro, mas funciona)
            current = get_user_balance(external_id)
            new_balance = current + grains
            r2 = httpx.patch(
                _url("users"),
                headers=_headers(),
                params={"external_id": f"eq.{external_id}"},
                json={"balance_grains": new_balance},
                timeout=10,
            )
            r2.raise_for_status()
            return True
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"add_grains erro: {e}")
        return False


def deduct_grains(external_id: str, grains: float) -> bool:
    """
    Debita Grains do usuario (sem deixar negativo).

    Usa RPC atomica `deduct_grains` quando disponível (evita race condition).
    Fallback: leitura + patch em série — seguro para baixo volume,
    mas sujeito a corrida em cenários de alta concorrência.
    """
    if not _check_config():
        return False
    try:
        # Tenta RPC atomica primeiro (Postgres-level update com CHECK balance >= 0)
        resp = httpx.post(
            f"{_get_url()}/rest/v1/rpc/deduct_grains",
            headers=_headers(),
            json={"p_external_id": external_id, "p_amount": grains},
            timeout=10,
        )
        if resp.status_code not in (404, 405):
            resp.raise_for_status()
            return True
        # RPC não existe ainda — fallback com leitura + patch
        current = get_user_balance(external_id)
        new_balance = max(0.0, current - grains)
        r2 = httpx.patch(
            _url("users"),
            headers=_headers(),
            params={"external_id": f"eq.{external_id}"},
            json={"balance_grains": new_balance},
            timeout=10,
        )
        r2.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"deduct_grains erro: {e}")
        return False


# ─── Pagamentos ───────────────────────────────────────────────────────────────

def is_signature_known(tx_signature: str) -> bool:
    """Verifica se a assinatura ja foi processada (anti-replay)."""
    if not _check_config():
        return False
    try:
        resp = httpx.get(
            _url("payment_history"),
            headers=_headers(),
            params={"tx_signature": f"eq.{tx_signature}", "select": "id"},
            timeout=10,
        )
        resp.raise_for_status()
        return len(resp.json()) > 0
    except Exception as e:
        logger.error(f"is_signature_known erro: {e}")
        return False


def record_payment(
    user_external_id: str,
    tx_signature: str | None,
    usdc_amount: float,
    grains_credited: float,
    status: str,
    qr_reference: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any] | None:
    """Registra um pagamento no historico."""
    if not _check_config():
        return None
    try:
        payload: dict[str, Any] = {
            "user_external_id": user_external_id,
            "usdc_amount": usdc_amount,
            "grains_credited": grains_credited,
            "status": status,
        }
        if tx_signature:
            payload["tx_signature"] = tx_signature
        if qr_reference:
            payload["qr_reference"] = qr_reference
        if expires_at:
            payload["expires_at"] = expires_at

        resp = httpx.post(
            _url("payment_history"),
            headers=_headers(),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as e:
        logger.error(f"record_payment erro: {e}")
        return None


def get_payment_by_reference(qr_reference: str) -> dict[str, Any] | None:
    """Busca sessao de pagamento pelo reference do QR."""
    if not _check_config():
        return None
    try:
        resp = httpx.get(
            _url("payment_history"),
            headers=_headers(),
            params={"qr_reference": f"eq.{qr_reference}", "select": "*", "order": "created_at.desc", "limit": "1"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as e:
        logger.error(f"get_payment_by_reference erro: {e}")
        return None


def update_payment_status(qr_reference: str, status: str, tx_signature: str | None = None, grains_credited: float | None = None) -> bool:
    """Atualiza status de uma sessao de pagamento."""
    if not _check_config():
        return False
    try:
        payload: dict[str, Any] = {"status": status}
        if tx_signature:
            payload["tx_signature"] = tx_signature
        if grains_credited is not None:
            payload["grains_credited"] = grains_credited

        resp = httpx.patch(
            _url("payment_history"),
            headers=_headers(),
            params={"qr_reference": f"eq.{qr_reference}"},
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"update_payment_status erro: {e}")
        return False


def get_payment_history(user_external_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Lista historico de pagamentos do usuario."""
    if not _check_config():
        return []
    try:
        resp = httpx.get(
            _url("payment_history"),
            headers=_headers(),
            params={
                "user_external_id": f"eq.{user_external_id}",
                "select": "id,usdc_amount,grains_credited,status,created_at,tx_signature",
                "order": "created_at.desc",
                "limit": str(limit),
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"get_payment_history erro: {e}")
        return []


# ─── Pending Credits (garantia de crédito sem perda de fundos) ───────────────

def insert_pending_credit(
    tx_signature: str,
    user_id: str,
    grains: float,
    usdc_amount: float,
) -> bool:
    """
    Registra um crédito pendente ANTES de chamar add_grains.
    Usa INSERT com ON CONFLICT DO NOTHING (idempotente via UNIQUE tx_signature).
    Retorna True se inserido (novo) ou False se já existia.
    """
    if not _check_config():
        return False
    try:
        resp = httpx.post(
            _url("pending_credits"),
            headers={**_headers(), "Prefer": "resolution=ignore-duplicates,return=representation"},
            json={
                "tx_signature": tx_signature,
                "user_id":      user_id,
                "grains":       grains,
                "usdc_amount":  usdc_amount,
                "status":       "pending",
                "attempts":     0,
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return bool(data)
        if resp.status_code == 409:
            return False  # já existia — não é erro
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"insert_pending_credit erro: {e}")
        return False


def mark_pending_credit_done(tx_signature: str) -> bool:
    """Marca pending_credit como 'credited' após add_grains bem-sucedido."""
    if not _check_config():
        return False
    try:
        resp = httpx.patch(
            _url("pending_credits"),
            headers=_headers(),
            params={"tx_signature": f"eq.{tx_signature}"},
            json={"status": "credited", "credited_at": datetime.now(timezone.utc).isoformat()},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"mark_pending_credit_done erro: {e}")
        return False


def increment_pending_credit_attempts(tx_signature: str) -> bool:
    """Incrementa o contador de tentativas (chamado quando add_grains falha)."""
    if not _check_config():
        return False
    try:
        r = httpx.get(
            _url("pending_credits"),
            headers=_headers(),
            params={"tx_signature": f"eq.{tx_signature}", "select": "attempts"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        current = int(data[0]["attempts"]) if data else 0
        resp = httpx.patch(
            _url("pending_credits"),
            headers=_headers(),
            params={"tx_signature": f"eq.{tx_signature}"},
            json={"attempts": current + 1},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"increment_pending_credit_attempts erro: {e}")
        return False


def get_pending_credits_to_retry(max_attempts: int = 10) -> list[dict]:
    """Retorna todos os pending_credits com status='pending' e attempts < max."""
    if not _check_config():
        return []
    try:
        resp = httpx.get(
            _url("pending_credits"),
            headers=_headers(),
            params={
                "status":   "eq.pending",
                "attempts": f"lt.{max_attempts}",
                "select":   "tx_signature,user_id,grains,usdc_amount,attempts",
                "order":    "created_at.asc",
                "limit":    "50",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"get_pending_credits_to_retry erro: {e}")
        return []


def get_credit_status(tx_signature: str) -> dict | None:
    """Retorna o status de um pending_credit pelo tx_signature."""
    if not _check_config():
        return None
    try:
        resp = httpx.get(
            _url("pending_credits"),
            headers=_headers(),
            params={"tx_signature": f"eq.{tx_signature}", "select": "status,user_id,grains,attempts,credited_at"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as e:
        logger.error(f"get_credit_status erro: {e}")
        return None


# ─── Custo de API ─────────────────────────────────────────────────────────────

def record_api_cost(
    user_external_id: str,
    provider: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    grains_debited: float,
    markup: float,
    session_id: str,
    # ProfitEngine fields (added in migration 002)
    model_tier: str = "MODEL_BASIC",
    infra_fee_grains: float = 0.0,
    operation: str = "chat",
) -> bool:
    """Registra custo de chamada de API (inclui campos ProfitEngine da migration 002)."""
    if not _check_config():
        return False
    try:
        resp = httpx.post(
            _url("api_cost_log"),
            headers=_headers(),
            json={
                "user_external_id": user_external_id,
                "provider":         provider,
                "tokens_in":        tokens_in,
                "tokens_out":       tokens_out,
                "cost_usd":         cost_usd,
                "grains_debited":   grains_debited,
                "markup":           markup,
                "session_id":       session_id,
                "model_tier":       model_tier,
                "infra_fee_grains": infra_fee_grains,
                "operation":        operation,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"record_api_cost erro: {e}")
        return False


# ─── Funcoes de Admin (agregacao via RPC Postgres) ────────────────────────────

def _rpc_call(fn_name: str) -> float | int | None:
    """
    Chama uma RPC Postgres via Supabase REST.
    Retorna None se nao configurado ou se a RPC nao existir.
    """
    if not _check_config():
        return None
    try:
        resp = httpx.post(
            f"{_get_url()}/rest/v1/rpc/{fn_name}",
            headers=_headers(),
            json={},
            timeout=15,
        )
        if resp.status_code == 404:
            return None   # RPC nao criada ainda
        resp.raise_for_status()
        val = resp.json()
        return val if val is not None else 0
    except Exception as e:
        logger.error(f"rpc_call({fn_name}) erro: {e}")
        return None


def _fallback_sum_table(table: str, column: str, where: str = "") -> float:
    """
    Fallback Python: busca registros e soma localmente.
    Usado quando a RPC nao esta disponivel no Supabase.
    Limitado a 1000 registros — suficiente para estimativas.
    """
    if not _check_config():
        return 0.0
    try:
        params: dict[str, str] = {"select": column, "limit": "1000"}
        if where:
            k, v = where.split("=", 1)
            params[k.strip()] = f"eq.{v.strip()}"
        resp = httpx.get(_url(table), headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
        return sum(float(r.get(column, 0) or 0) for r in rows)
    except Exception as e:
        logger.error(f"fallback_sum({table}.{column}) erro: {e}")
        return 0.0


def admin_sum_usdc_received() -> float:
    """Total de USDC recebido (pagamentos finalizados)."""
    val = _rpc_call("sum_usdc_received")
    if val is None:
        val = _fallback_sum_table("payment_history", "usdc_amount", "status=finalized")
    return float(val)


def admin_sum_api_spend_usd() -> float:
    """Total gasto bruto em APIs (USD custo base, sem markup)."""
    val = _rpc_call("sum_api_spend_usd")
    if val is None:
        val = _fallback_sum_table("api_cost_log", "cost_usd")
    return float(val)


def admin_sum_grains_debited() -> float:
    """Total de Grains debitados por uso de API."""
    val = _rpc_call("sum_grains_debited")
    if val is None:
        val = _fallback_sum_table("api_cost_log", "grains_debited")
    return float(val)


def admin_sum_grains_credited() -> float:
    """Total de Grains creditados por recargas USDC."""
    val = _rpc_call("sum_grains_credited")
    if val is None:
        val = _fallback_sum_table("payment_history", "grains_credited", "status=finalized")
    return float(val)


def admin_count_active_recharges() -> int:
    """Numero de sessoes de pagamento pendentes."""
    val = _rpc_call("count_active_recharges")
    if val is None:
        if not _check_config():
            return 0
        try:
            resp = httpx.get(
                _url("payment_history"),
                headers=_headers(),
                params={"status": "eq.pending", "select": "id"},
                timeout=10,
            )
            resp.raise_for_status()
            return len(resp.json())
        except Exception:
            return 0
    return int(val)


def admin_sum_user_balances() -> float:
    """Total de Grains em circulacao (soma dos saldos de todos os usuarios)."""
    val = _rpc_call("sum_user_balances")
    if val is None:
        val = _fallback_sum_table("users", "balance_grains")
    return float(val)


# ─── Reconciliacao de Tesouraria ──────────────────────────────────────────────

def record_reconciliation(
    grains_in_circulation: float,
    usdc_liability: float,
    usdc_on_chain: float | None,
    needs_rebalancing: bool | None,
    status: str,
    wallet: str = "",
) -> bool:
    """
    Persiste uma entrada no reconciliation_log (migration 003).
    Chamado apos cada checagem do endpoint /admin-stats/reconciliation.
    Falha silenciosa — nao bloqueia a resposta ao admin.
    """
    if not _check_config():
        return False
    try:
        payload: dict[str, Any] = {
            "grains_in_circulation": grains_in_circulation,
            "usdc_liability":        usdc_liability,
            "status":                status,
        }
        if usdc_on_chain is not None:
            payload["usdc_on_chain"] = usdc_on_chain
        if needs_rebalancing is not None:
            payload["needs_rebalancing"] = needs_rebalancing
        if wallet:
            payload["wallet"] = wallet

        resp = httpx.post(
            _url("reconciliation_log"),
            headers=_headers(),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"record_reconciliation erro (nao critico): {e}")
        return False


def admin_get_recent_reconciliations(limit: int = 50) -> list[dict[str, Any]]:
    """Busca as ultimas N entradas do reconciliation_log."""
    if not _check_config():
        return []
    try:
        resp = httpx.get(
            _url("reconciliation_log"),
            headers=_headers(),
            params={
                "select": "id,grains_in_circulation,usdc_liability,usdc_on_chain,needs_rebalancing,status,wallet,checked_at",
                "order": "checked_at.desc",
                "limit": str(limit),
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"admin_get_recent_reconciliations erro: {e}")
        return []