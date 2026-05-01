"""
Luna Pay-Flow — CostController (v2)
Delega calculo de markup ao ProfitEngine (tiered) com fallback para markup flat.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.payments import supabase_client as db

logger = logging.getLogger("luna.payments.cost")

# Mantido por backward-compat / fallback se ProfitEngine falhar no import
API_COST_MARKUP = float(os.getenv("API_COST_MARKUP", "2.2"))  # deprecated
GRAINS_PER_USD  = float(os.getenv("GRAINS_PER_USDC", "1000"))
BUFFER_FACTOR   = 1.10

# Tenta importar o ProfitEngine; se falhar, usa markup flat como fallback
try:
    from app.payments.grains_manager import get_profit_engine, INFRA_FEE_GRAINS
    _PROFIT_ENGINE_AVAILABLE = True
except Exception as _ie:
    logger.warning(f"ProfitEngine nao disponivel — usando markup flat 2.2x: {_ie}")
    _PROFIT_ENGINE_AVAILABLE = False
    INFRA_FEE_GRAINS = 0.0

# ─── Tabela de custo base (USD por 1.000 tokens) ─────────────────────────────
COST_TABLE: dict[str, dict[str, float]] = {
    # OpenAI
    "openai":            {"in": 0.0050, "out": 0.0150},
    "gpt-4o":            {"in": 0.0050, "out": 0.0150},
    "gpt-4o-mini":       {"in": 0.0001, "out": 0.0003},
    "gpt-4":             {"in": 0.0300, "out": 0.0600},
    "gpt-3.5-turbo":     {"in": 0.0005, "out": 0.0015},
    # Groq
    "groq":              {"in": 0.0001, "out": 0.0001},
    "groq-llama3":       {"in": 0.0001, "out": 0.0001},
    "groq-mixtral":      {"in": 0.0002, "out": 0.0002},
    # Anthropic
    "anthropic":         {"in": 0.0030, "out": 0.0150},
    "claude-3-5-sonnet": {"in": 0.0030, "out": 0.0150},
    "claude-3-opus":     {"in": 0.0150, "out": 0.0750},
    "claude-3-haiku":    {"in": 0.0002, "out": 0.0001},
    # Together AI
    "together":          {"in": 0.0009, "out": 0.0009},
    "llama-405b":        {"in": 0.0009, "out": 0.0009},
    "llama-3.1-405b":    {"in": 0.0009, "out": 0.0009},
    "mixtral-8x7b":      {"in": 0.0006, "out": 0.0006},
    # Seguranca / Imagem (custo estimado por execucao normalizado por 1k tokens)
    "hunter-v2":         {"in": 0.0050, "out": 0.0200},
    "hunter-scan":       {"in": 0.0050, "out": 0.0200},
    "image-analysis":    {"in": 0.0000, "out": 0.0200},
    "video-analysis":    {"in": 0.0000, "out": 0.0400},
    "dall-e-3":          {"in": 0.0000, "out": 0.0400},
    # Fallback
    "default":           {"in": 0.0050, "out": 0.0150},
}


# ─── Excecao ──────────────────────────────────────────────────────────────────

class InsufficientGrainsError(Exception):
    def __init__(self, available: float, required: float):
        self.available = available
        self.required  = required
        super().__init__(
            f"Saldo insuficiente: {available:.2f} Grains disponiveis, "
            f"{required:.2f} necessarios. Acesse /payflow para recarregar."
        )


# ─── CostController (v2) ──────────────────────────────────────────────────────

class CostController:
    """
    Calcula, reserva e debita Grains por chamadas de API.
    Delega markup ao ProfitEngine (tiered 2.0x/2.5x/3.0x).
    """

    def _get_cost_rates(self, provider: str) -> dict[str, float]:
        key = (provider or "").lower().strip()
        return COST_TABLE.get(key) or COST_TABLE["default"]

    def estimate_cost_usd(self, provider: str, tokens_in: int, tokens_out: int) -> float:
        """Custo bruto em USD sem markup."""
        rates = self._get_cost_rates(provider)
        return (tokens_in / 1000) * rates["in"] + (tokens_out / 1000) * rates["out"]

    def estimate_cost_grains(
        self,
        provider: str,
        tokens_in: int,
        tokens_out: int,
        operation: str = "chat",
    ) -> float:
        """
        Custo total em Grains com markup tiered aplicado.
        Delega ao ProfitEngine; fallback para markup flat 2.2x.
        """
        cost_usd = self.estimate_cost_usd(provider, tokens_in, tokens_out)

        if _PROFIT_ENGINE_AVAILABLE:
            engine = get_profit_engine()
            result = engine.calculate_final_grains(cost_usd, provider, operation)
            return result["grains_total"]

        # Fallback flat
        return cost_usd * API_COST_MARKUP * GRAINS_PER_USD

    def check_and_reserve(
        self,
        user_id: str,
        estimated_tokens_in: int = 500,
        estimated_tokens_out: int = 500,
        provider: str = "openai",
        operation: str = "chat",
    ) -> float:
        """
        Verifica saldo antes de chamar a API (pre-flight estimate).
        Aplica buffer de 10% sobre a estimativa.
        Lanca InsufficientGrainsError se saldo insuficiente.
        """
        estimated_grains  = self.estimate_cost_grains(provider, estimated_tokens_in, estimated_tokens_out, operation)
        required_with_buf = estimated_grains * BUFFER_FACTOR
        available         = db.get_user_balance(user_id)

        logger.debug(
            f"pre-flight | user={user_id} provider={provider} op={operation} "
            f"est={estimated_grains:.4f}G buf={required_with_buf:.4f}G avail={available:.4f}G"
        )

        if available < required_with_buf:
            raise InsufficientGrainsError(available=available, required=required_with_buf)

        return estimated_grains

    def debit(
        self,
        user_id: str,
        provider: str,
        tokens_in: int,
        tokens_out: int,
        session_id: str = "",
        operation: str = "chat",
    ) -> float:
        """
        Debita Grains do usuario com base no consumo real de tokens.
        Registra breakdown completo em api_cost_log.
        """
        cost_usd = self.estimate_cost_usd(provider, tokens_in, tokens_out)

        if _PROFIT_ENGINE_AVAILABLE:
            engine   = get_profit_engine()
            breakdown = engine.calculate_final_grains(cost_usd, provider, operation)
            grains_debited  = breakdown["grains_total"]
            model_tier      = breakdown["tier"]
            infra_fee       = breakdown["infra_fee"]
            effective_markup = breakdown["markup"]
        else:
            grains_debited   = cost_usd * API_COST_MARKUP * GRAINS_PER_USD
            model_tier       = "MODEL_EXPERT"
            infra_fee        = 0.0
            effective_markup = API_COST_MARKUP

        db.deduct_grains(user_id, grains_debited)
        db.record_api_cost(
            user_external_id  = user_id,
            provider          = provider,
            tokens_in         = tokens_in,
            tokens_out        = tokens_out,
            cost_usd          = cost_usd,
            grains_debited    = grains_debited,
            markup            = effective_markup,
            session_id        = session_id,
            model_tier        = model_tier,
            infra_fee_grains  = infra_fee,
            operation         = operation,
        )

        logger.info(
            f"debit | user={user_id} provider={provider} tier={model_tier} "
            f"markup={effective_markup}x op={operation} "
            f"in={tokens_in} out={tokens_out} usd={cost_usd:.6f} "
            f"grains={grains_debited:.4f} (infra={infra_fee})"
        )

        return grains_debited

    def cost_summary(
        self,
        provider: str,
        tokens_in: int,
        tokens_out: int,
        operation: str = "chat",
    ) -> dict[str, Any]:
        """Resumo de custo enriquecido para exibicao ao usuario/frontend."""
        cost_usd = self.estimate_cost_usd(provider, tokens_in, tokens_out)
        rates    = self._get_cost_rates(provider)

        if _PROFIT_ENGINE_AVAILABLE:
            engine    = get_profit_engine()
            breakdown = engine.calculate_final_grains(cost_usd, provider, operation)
            profit    = engine.profit_breakdown(cost_usd, provider, operation)
            return {
                "provider":        provider,
                "operation":       operation,
                "tokens_in":       tokens_in,
                "tokens_out":      tokens_out,
                "cost_usd":        round(cost_usd, 8),
                "effective_markup": breakdown["markup"],
                "tier":            breakdown["tier"],
                "grains_api":      breakdown["grains_api"],
                "infra_fee":       breakdown["infra_fee"],
                "grains_total":    breakdown["grains_total"],
                "floor_applied":   breakdown["floor_applied"],
                "revenue_usd":     profit["revenue_usd"],
                "profit_usd":      profit["profit_usd"],
                "margin_pct":      profit["margin_pct"],
                "rate_in":         rates["in"],
                "rate_out":        rates["out"],
                # compat legado
                "markup":          breakdown["markup"],
                "grains":          breakdown["grains_total"],
            }

        # Fallback
        grains = cost_usd * API_COST_MARKUP * GRAINS_PER_USD
        return {
            "provider":   provider,
            "operation":  operation,
            "tokens_in":  tokens_in,
            "tokens_out": tokens_out,
            "cost_usd":   round(cost_usd, 8),
            "markup":     API_COST_MARKUP,
            "grains":     round(grains, 4),
            "rate_in":    rates["in"],
            "rate_out":   rates["out"],
        }


# ─── Singleton ────────────────────────────────────────────────────────────────

_controller: CostController | None = None


def get_cost_controller() -> CostController:
    global _controller
    if _controller is None:
        _controller = CostController()
    return _controller