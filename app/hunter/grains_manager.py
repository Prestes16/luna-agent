"""
Luna Grains Manager
====================
Sistema de créditos para rastrear consumo de tokens LLM com markup comercial.

Hierarquia de Custo:
  Tier 0 (Free):    Groq Llama-3-8B  — triagem rápida, custo zero (quota generosa)
  Tier 1 (Expert):  Together AI 405B — audit profundo, markup 1.5x
  Tier 2 (Deep):    DeepSeek-Coder   — análise de código específica, markup 1.5x
  Tier 3 (Premium): OpenAI GPT-4o    — fallback premium, markup 2.2x

1 Grain = 0.001 USD  →  1 USD = 1000 Grains
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("luna.grains")

# ─── Tabela de Preços (USD por 1M tokens) ─────────────────────────────────────

TOKEN_COSTS_USD_PER_1M: dict[str, dict] = {
    # Tier 0 — Free / Ultra-low cost
    "groq/llama-3-8b-instant":       {"input": 0.05,  "output": 0.08,  "tier": 0},
    "groq/llama3-8b-8192":           {"input": 0.05,  "output": 0.08,  "tier": 0},
    "groq/llama-3.1-8b-instant":     {"input": 0.05,  "output": 0.08,  "tier": 0},

    # Tier 1 — Expert (markup 1.5x)
    "together/meta-llama/llama-3.1-405b-instruct-turbo": {
        "input": 5.00, "output": 5.00, "tier": 1,
    },
    "together/meta-llama/llama-3.1-70b-instruct-turbo": {
        "input": 0.90, "output": 0.90, "tier": 1,
    },
    "together/deepseek-ai/deepseek-coder-v2": {
        "input": 0.14, "output": 0.28, "tier": 1,
    },
    "groq/llama-3.1-70b-versatile":  {"input": 0.59,  "output": 0.79,  "tier": 1},
    "groq/llama-3.3-70b-versatile":  {"input": 0.59,  "output": 0.79,  "tier": 1},
    "groq/mixtral-8x7b-32768":       {"input": 0.24,  "output": 0.24,  "tier": 1},

    # Tier 2 — Gemini (markup 1.5x)
    "gemini/gemini-1.5-pro":         {"input": 3.50,  "output": 10.50, "tier": 2},
    "gemini/gemini-1.5-flash":       {"input": 0.075, "output": 0.30,  "tier": 2},

    # Tier 3 — Premium (markup 2.2x)
    "openai/gpt-4o":                 {"input": 2.50,  "output": 10.00, "tier": 3},
    "openai/gpt-4o-mini":            {"input": 0.15,  "output": 0.60,  "tier": 3},
    "openai/gpt-4-turbo":            {"input": 10.00, "output": 30.00, "tier": 3},
}

# Markup por tier
TIER_MARKUP: dict[int, float] = {
    0: 1.0,   # free tier — sem markup
    1: 1.5,   # expert markup
    2: 1.5,   # gemini markup
    3: 2.2,   # premium markup
}

GRAINS_PER_USD = 1000  # 1 USD = 1000 Grains
DEFAULT_GRAINS  = 10_000  # saldo inicial


# ─── Registro de uso ──────────────────────────────────────────────────────────

@dataclass
class GrainsTransaction:
    timestamp:     float
    operation:     str     # "audit_triage", "audit_deep", "poc_gen", "report_gen", "chat"
    provider:      str
    model:         str
    tier:          int
    input_tokens:  int
    output_tokens: int
    raw_cost_usd:  float
    markup:        float
    final_cost_usd: float
    grains_spent:  int
    context:       str     # ex: "hunt:/path/to/program"


@dataclass
class GrainsState:
    balance: int = DEFAULT_GRAINS
    total_spent: int = 0
    transactions: list[GrainsTransaction] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)


# ─── Manager ──────────────────────────────────────────────────────────────────

class GrainsManager:
    """
    Rastreia consumo de tokens e debita Grains do saldo do usuário.

    Uso:
        gm = GrainsManager()
        # Antes de chamar o LLM — estimar custo
        est = gm.estimate(provider="groq", model="llama-3-8b-instant",
                          estimated_input=2000, estimated_output=800)
        # Após o LLM retornar — debitar custo real
        gm.debit(provider="together",
                 model="meta-llama/Llama-3.1-405B-Instruct-Turbo",
                 input_tokens=resp.usage.prompt_tokens,
                 output_tokens=resp.usage.completion_tokens,
                 operation="audit_deep", context="hunt:/path")
    """

    _STORE_PATH = Path("data/grains_state.json")

    def __init__(self, store_path: Optional[Path] = None) -> None:
        self._path = Path(store_path) if store_path else self._STORE_PATH
        self._state = self._load()

    # ── Persistência ─────────────────────────────────────────────────────

    def _load(self) -> GrainsState:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text("utf-8"))
                txs = [GrainsTransaction(**t) for t in raw.pop("transactions", [])]
                state = GrainsState(**raw)
                state.transactions = txs
                return state
            except Exception as e:
                logger.warning(f"[grains] Erro ao carregar estado: {e}. Reiniciando.")
        return GrainsState()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._state.last_updated = time.time()
        data = asdict(self._state)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")

    # ── Lookup de custo ───────────────────────────────────────────────────

    def _lookup(self, provider: str, model: str) -> dict:
        """Localiza custo/tier para (provider, model). Normaliza o modelo."""
        model_lower = model.lower()
        # Chave normalizada: "provider/model"
        key = f"{provider.lower()}/{model_lower}"
        if key in TOKEN_COSTS_USD_PER_1M:
            return TOKEN_COSTS_USD_PER_1M[key]

        # Busca parcial — útil para modelos com sufixos de versão
        for k, v in TOKEN_COSTS_USD_PER_1M.items():
            if k.startswith(f"{provider.lower()}/") and model_lower.split(":")[0] in k:
                return v

        # Default: tier 1 com custo médio
        logger.debug(f"[grains] Modelo não mapeado: {provider}/{model} — usando custo padrão tier-1")
        return {"input": 1.0, "output": 1.0, "tier": 1}

    def _calculate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[float, float, float, int]:
        """
        Retorna (raw_cost_usd, markup, final_cost_usd, grains_spent).
        """
        cost_table = self._lookup(provider, model)
        tier = cost_table.get("tier", 1)
        markup = TIER_MARKUP.get(tier, 1.5)

        raw_usd = (
            input_tokens  / 1_000_000 * cost_table["input"] +
            output_tokens / 1_000_000 * cost_table["output"]
        )
        final_usd = raw_usd * markup
        grains = max(1, round(final_usd * GRAINS_PER_USD))
        return raw_usd, markup, final_usd, grains

    # ── API Pública ───────────────────────────────────────────────────────

    @property
    def balance(self) -> int:
        return self._state.balance

    def estimate(
        self,
        provider: str,
        model: str,
        estimated_input: int,
        estimated_output: int,
    ) -> dict:
        """Estima custo sem debitar."""
        raw, markup, final, grains = self._calculate_cost(
            provider, model, estimated_input, estimated_output
        )
        tier = self._lookup(provider, model).get("tier", 1)
        return {
            "provider": provider,
            "model": model,
            "tier": tier,
            "estimated_input_tokens": estimated_input,
            "estimated_output_tokens": estimated_output,
            "raw_cost_usd": round(raw, 6),
            "markup": markup,
            "final_cost_usd": round(final, 6),
            "grains_cost": grains,
            "current_balance": self._state.balance,
            "affordable": self._state.balance >= grains,
        }

    def debit(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        operation: str = "chat",
        context: str = "",
    ) -> GrainsTransaction:
        """Debita Grains pelo uso real de tokens."""
        raw, markup, final, grains = self._calculate_cost(
            provider, model, input_tokens, output_tokens
        )
        tier = self._lookup(provider, model).get("tier", 1)

        tx = GrainsTransaction(
            timestamp=time.time(),
            operation=operation,
            provider=provider,
            model=model,
            tier=tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw_cost_usd=round(raw, 6),
            markup=markup,
            final_cost_usd=round(final, 6),
            grains_spent=grains,
            context=context,
        )

        self._state.balance = max(0, self._state.balance - grains)
        self._state.total_spent += grains
        self._state.transactions.append(tx)

        # Manter só últimas 500 transações
        if len(self._state.transactions) > 500:
            self._state.transactions = self._state.transactions[-500:]

        self._save()
        logger.info(
            f"[grains] -{grains}g  op={operation}  provider={provider}/{model}  "
            f"tokens={input_tokens}+{output_tokens}  saldo={self._state.balance}g"
        )
        return tx

    def top_up(self, grains: int, reason: str = "manual") -> None:
        """Adiciona Grains ao saldo."""
        self._state.balance += grains
        self._save()
        logger.info(f"[grains] +{grains}g  reason={reason}  saldo={self._state.balance}g")

    def get_summary(self) -> dict:
        """Resumo do saldo e consumo."""
        txs = self._state.transactions
        by_op: dict[str, int] = {}
        by_tier: dict[int, int] = {}
        for tx in txs:
            by_op[tx.operation] = by_op.get(tx.operation, 0) + tx.grains_spent
            by_tier[tx.tier] = by_tier.get(tx.tier, 0) + tx.grains_spent

        return {
            "balance_grains": self._state.balance,
            "balance_usd": round(self._state.balance / GRAINS_PER_USD, 4),
            "total_spent_grains": self._state.total_spent,
            "total_spent_usd": round(self._state.total_spent / GRAINS_PER_USD, 4),
            "transactions_count": len(txs),
            "by_operation": by_op,
            "by_tier": by_tier,
            "last_5_transactions": [
                {
                    "op":     t.operation,
                    "model":  f"{t.provider}/{t.model.split('/')[-1][:20]}",
                    "tokens": f"{t.input_tokens}+{t.output_tokens}",
                    "grains": t.grains_spent,
                    "usd":    round(t.final_cost_usd, 5),
                }
                for t in reversed(txs[-5:])
            ],
        }

    def render_status(self) -> str:
        """Retorna string formatada para exibição no terminal."""
        s = self.get_summary()
        lines = [
            f"💎 Luna Grains — Saldo: {s['balance_grains']:,}g  (≈ ${s['balance_usd']:.4f} USD)",
            f"   Total gasto: {s['total_spent_grains']:,}g  (${s['total_spent_usd']:.4f})",
            f"   Transações: {s['transactions_count']}",
        ]
        if s["by_operation"]:
            ops = ", ".join(f"{k}: {v}g" for k, v in sorted(s["by_operation"].items(), key=lambda x: -x[1])[:5])
            lines.append(f"   Por operação: {ops}")
        return "\n".join(lines)


# ─── Singleton ────────────────────────────────────────────────────────────────

_grains_manager: GrainsManager | None = None


def get_grains_manager() -> GrainsManager:
    global _grains_manager
    if _grains_manager is None:
        _grains_manager = GrainsManager()
    return _grains_manager
