"""
Luna Pay-Flow — GrainsManager / ProfitEngine
Matematica de precificacao tiered com markup escalonado por tipo de modelo.

Regra de Ouro:
    Price_Final = max(API_Cost_USD * Markup * GRAINS_PER_USD, Floor) + INFRA_FEE

Tiers:
    MODEL_BASIC    (2.0x) — modelos de volume (Llama-8B, GPT-3.5, Groq)
    MODEL_EXPERT   (2.5x) — modelos de valor tecnico (GPT-4o, Claude Sonnet, 405B)
    MODEL_SECURITY (3.0x) — analise de seguranca e imagem (Hunter, Image/Video)
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger("luna.payments.grains")

# ─── Constantes de conversao ──────────────────────────────────────────────────
# $0.01 USD = 10 Grains  →  $1 USD = 1000 Grains
GRAINS_PER_USD: float = float(os.getenv("GRAINS_PER_USDC", "1000"))

# Taxa fixa de infra por requisicao bem-sucedida
INFRA_FEE_GRAINS: float = float(os.getenv("INFRA_FEE_GRAINS", "0.5"))

# ─── Tiers de modelo ─────────────────────────────────────────────────────────
MODEL_BASIC    = "MODEL_BASIC"
MODEL_EXPERT   = "MODEL_EXPERT"
MODEL_SECURITY = "MODEL_SECURITY"

# Markups configuráveis via env (com defaults do plano)
_MARKUP_BASIC    = float(os.getenv("MARKUP_MODEL_BASIC",    "2.0"))
_MARKUP_EXPERT   = float(os.getenv("MARKUP_MODEL_EXPERT",   "2.5"))
_MARKUP_SECURITY = float(os.getenv("MARKUP_MODEL_SECURITY", "3.0"))

TIER_MARKUPS: dict[str, float] = {
    MODEL_BASIC:    _MARKUP_BASIC,
    MODEL_EXPERT:   _MARKUP_EXPERT,
    MODEL_SECURITY: _MARKUP_SECURITY,
}

# Mapeamento provider (lower) → tier
_PROVIDER_TIER_MAP: dict[str, str] = {
    # ── MODEL_BASIC (2.0x) — volume ───────────────────────────────────────────
    "groq":          MODEL_BASIC,
    "groq-llama3":   MODEL_BASIC,
    "groq-mixtral":  MODEL_BASIC,
    "llama-3-8b":    MODEL_BASIC,
    "llama-3.1-8b":  MODEL_BASIC,
    "gpt-3.5-turbo": MODEL_BASIC,
    "gpt-4o-mini":   MODEL_BASIC,
    "claude-3-haiku": MODEL_BASIC,
    # ── MODEL_EXPERT (2.5x) — valor tecnico ───────────────────────────────────
    "openai":           MODEL_EXPERT,
    "gpt-4o":           MODEL_EXPERT,
    "gpt-4":            MODEL_EXPERT,
    "anthropic":        MODEL_EXPERT,
    "claude-3-5-sonnet": MODEL_EXPERT,
    "claude-3-opus":    MODEL_EXPERT,
    "together":         MODEL_EXPERT,
    "llama-405b":       MODEL_EXPERT,
    "llama-3.1-405b":   MODEL_EXPERT,
    "meta-llama/llama-3.1-405b-instruct-turbo": MODEL_EXPERT,
    "mixtral-8x7b":     MODEL_EXPERT,
    # ── MODEL_SECURITY (3.0x) — seguranca e processamento pesado ─────────────
    "hunter-v2":           MODEL_SECURITY,
    "hunter-scan":         MODEL_SECURITY,
    "image-analysis":      MODEL_SECURITY,
    "video-analysis":      MODEL_SECURITY,
    "image_video_analysis": MODEL_SECURITY,
    "stability":           MODEL_SECURITY,
    "dall-e-3":            MODEL_SECURITY,
}

# Preco minimo garantido (floor) por tipo de operacao
# Garante margens minimas conforme tabela Luna Power
OPERATION_FLOOR: dict[str, float] = {
    "luna_chat_message":    0.10,   # ~100% margem em chat basico
    "hunter_scan_1k":      15.00,   # ~200% margem em analise de seguranca
    "image_video_analysis": 50.00,  # ~150% margem em imagem/video
    "chat":                  0.0,   # sem floor para chat generico
    "default":               0.0,
}


# ─── ProfitEngine ─────────────────────────────────────────────────────────────

class ProfitEngine:
    """
    Motor de precificacao tiered da Luna.

    Aplica markup escalonado baseado no tipo de modelo e garante
    preco minimo (floor) por operacao para sustentar margens.
    """

    # ── Classificacao ──────────────────────────────────────────────────────────

    def classify_model(self, provider: str) -> str:
        """
        Retorna o tier de modelo para um provider.
        Default: MODEL_EXPERT se desconhecido.
        """
        key = (provider or "").lower().strip()
        return _PROVIDER_TIER_MAP.get(key, MODEL_EXPERT)

    def get_markup(self, provider: str) -> float:
        """Retorna o multiplicador de markup para um provider."""
        tier = self.classify_model(provider)
        return TIER_MARKUPS.get(tier, _MARKUP_EXPERT)

    # ── Calculo de preco ───────────────────────────────────────────────────────

    def calculate_final_grains(
        self,
        cost_usd: float,
        provider: str,
        operation: str = "chat",
    ) -> dict[str, Any]:
        """
        Calcula o preco final em Grains.

        Formula:
            grains_api   = cost_usd * markup * GRAINS_PER_USD
            grains_final = max(grains_api, floor[operation]) + INFRA_FEE

        Retorna dict com breakdown completo para auditoria.
        """
        tier      = self.classify_model(provider)
        markup    = TIER_MARKUPS.get(tier, _MARKUP_EXPERT)
        floor_key = operation if operation in OPERATION_FLOOR else "default"
        floor     = OPERATION_FLOOR.get(floor_key, 0.0)

        grains_api   = cost_usd * markup * GRAINS_PER_USD
        grains_above_floor = max(grains_api, floor)
        floor_applied      = grains_api < floor

        grains_total = grains_above_floor + INFRA_FEE_GRAINS

        logger.debug(
            f"ProfitEngine | provider={provider} tier={tier} markup={markup}x "
            f"cost_usd={cost_usd:.8f} grains_api={grains_api:.4f} "
            f"floor={floor} floor_applied={floor_applied} total={grains_total:.4f}"
        )

        return {
            "grains_total":   round(grains_total, 4),
            "grains_api":     round(grains_api, 4),
            "grains_floor":   round(floor, 4),
            "infra_fee":      INFRA_FEE_GRAINS,
            "markup":         markup,
            "tier":           tier,
            "floor_applied":  floor_applied,
            "cost_usd":       round(cost_usd, 8),
            "operation":      operation,
        }

    # ── Conversao direta ───────────────────────────────────────────────────────

    def usd_to_grains(self, usd: float) -> float:
        """Converte USD para Grains sem markup (taxa de cambio pura: $0.01 = 10 Grains)."""
        return usd * GRAINS_PER_USD

    def grains_to_usd(self, grains: float) -> float:
        """Converte Grains para USD (para calculos de reconciliacao)."""
        return grains / GRAINS_PER_USD if GRAINS_PER_USD else 0.0

    # ── Estimativa de lucro ────────────────────────────────────────────────────

    def profit_breakdown(
        self,
        cost_usd: float,
        provider: str,
        operation: str = "chat",
    ) -> dict[str, Any]:
        """
        Retorna breakdown completo de lucro para uma transacao.
        Util para o dashboard admin e logs de auditoria.
        """
        calc          = self.calculate_final_grains(cost_usd, provider, operation)
        revenue_usd   = self.grains_to_usd(calc["grains_total"])
        profit_usd    = revenue_usd - cost_usd
        margin_pct    = (profit_usd / revenue_usd * 100) if revenue_usd > 0 else 0.0

        return {
            **calc,
            "revenue_usd":  round(revenue_usd, 6),
            "profit_usd":   round(profit_usd, 6),
            "margin_pct":   round(margin_pct, 2),
        }

    # ── Preco por mensagem (conveniencia) ──────────────────────────────────────

    def price_chat_message(self, cost_usd: float, provider: str = "groq") -> dict[str, Any]:
        """Precifica uma unica mensagem de chat (operacao: luna_chat_message)."""
        return self.calculate_final_grains(cost_usd, provider, "luna_chat_message")

    def price_hunter_scan(self, cost_usd: float, provider: str = "llama-3.1-405b") -> dict[str, Any]:
        """Precifica um Hunter Scan por 1k tokens (operacao: hunter_scan_1k)."""
        return self.calculate_final_grains(cost_usd, provider, "hunter_scan_1k")

    def price_image_analysis(self, cost_usd: float, provider: str = "image-analysis") -> dict[str, Any]:
        """Precifica analise de imagem/video (operacao: image_video_analysis)."""
        return self.calculate_final_grains(cost_usd, provider, "image_video_analysis")


# ─── GrainsManager (wrapper de alto nivel) ───────────────────────────────────

class GrainsManager:
    """
    Gerenciador de alto nivel de Grains.
    Combina ProfitEngine com logica de conversao e relatorios.
    """

    def __init__(self):
        self.engine = ProfitEngine()

    @property
    def markup_tiers(self) -> dict[str, float]:
        return {
            MODEL_BASIC:    TIER_MARKUPS[MODEL_BASIC],
            MODEL_EXPERT:   TIER_MARKUPS[MODEL_EXPERT],
            MODEL_SECURITY: TIER_MARKUPS[MODEL_SECURITY],
        }

    def markup_for(self, provider: str) -> float:
        return self.engine.get_markup(provider)

    def tier_for(self, provider: str) -> str:
        return self.engine.classify_model(provider)

    def calculate(self, cost_usd: float, provider: str, operation: str = "chat") -> dict[str, Any]:
        return self.engine.calculate_final_grains(cost_usd, provider, operation)

    def recharge_grains(self, usdc_amount: float) -> float:
        """Quantos Grains o usuario recebe ao recarregar X USDC (taxa fixa)."""
        return usdc_amount * GRAINS_PER_USD

    def usdc_liability(self, grains_in_circulation: float) -> float:
        """Responsabilidade em USDC para a quantidade de Grains em circulacao."""
        return self.engine.grains_to_usd(grains_in_circulation)


# ─── Singletons ───────────────────────────────────────────────────────────────

_engine: ProfitEngine | None = None
_manager: GrainsManager | None = None


def get_profit_engine() -> ProfitEngine:
    global _engine
    if _engine is None:
        _engine = ProfitEngine()
    return _engine


def get_grains_manager() -> GrainsManager:
    global _manager
    if _manager is None:
        _manager = GrainsManager()
    return _manager