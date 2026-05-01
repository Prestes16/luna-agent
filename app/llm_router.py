"""
Luna Agent - LLM Router Elite v2.0
====================================
Roteamento multi-provedor com fallback automático em <1s.

Ordem de prioridade (configurável via .env LUNA_LLM_PRIORITY):
  1. Together AI  — Llama-3.1-405B / Llama-4 Maverick (128k, raciocínio superior)
  2. Groq         — Llama-3.1-70B / Mixtral (ultra-baixa latência, limite free generoso)
  3. Ollama Local — qualquer modelo instalado localmente (zero custo, offline)
  4. Gemini       — gemini-1.5-pro (1M context, fallback confiável)
  5. OpenAI       — gpt-4o (backup final)

Fallback ativado em:
  - HTTP 429 (rate limit)
  - HTTP 402 / "insufficient_credits" / "out of credits"
  - ConnectionError (Ollama offline)
  - Timeout > 8s no primeiro token
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Generator, Iterator, Optional

logger = logging.getLogger("luna.llm_router")


# ─── Provedores ───────────────────────────────────────────────────────────────

class Provider(str, Enum):
    TOGETHER   = "together"
    GROQ       = "groq"
    OLLAMA     = "ollama"
    GEMINI     = "gemini"
    OPENAI     = "openai"
    XAI        = "xai"
    ANTHROPIC  = "anthropic"


# ─── Modelos por provedor ─────────────────────────────────────────────────────

PROVIDER_MODELS: dict[Provider, list[dict]] = {
    Provider.TOGETHER: [
        {
            "id": "meta-llama/Llama-3.1-405B-Instruct-Turbo",
            "context": 128_000,
            "label": "Llama-3.1-405B (Together)",
            "supports_tools": True,
        },
        {
            "id": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
            "context": 128_000,
            "label": "Llama-4 Maverick (Together)",
            "supports_tools": True,
        },
        {
            "id": "meta-llama/Llama-3.1-70B-Instruct-Turbo",
            "context": 128_000,
            "label": "Llama-3.1-70B (Together)",
            "supports_tools": True,
        },
    ],
    Provider.GROQ: [
        {
            "id": "llama-3.1-70b-versatile",
            "context": 128_000,
            "label": "Llama-3.1-70B (Groq)",
            "supports_tools": True,
        },
        {
            "id": "llama-3.3-70b-versatile",
            "context": 128_000,
            "label": "Llama-3.3-70B (Groq)",
            "supports_tools": True,
        },
        {
            "id": "llama-3.1-8b-instant",
            "context": 128_000,
            "label": "Llama-3.1-8B-Instant (Groq)",
            "supports_tools": True,
        },
    ],
    Provider.OLLAMA: [
        {
            "id": "llama3.1:latest",
            "context": 128_000,
            "label": "Llama 3.1 (Local)",
            "supports_tools": False,
        },
        {
            "id": "mistral:latest",
            "context": 32_768,
            "label": "Mistral (Local)",
            "supports_tools": False,
        },
        {
            "id": "deepseek-coder:latest",
            "context": 32_768,
            "label": "DeepSeek Coder (Local)",
            "supports_tools": False,
        },
    ],
    Provider.GEMINI: [
        {
            "id": "gemini-1.5-pro",
            "context": 1_000_000,
            "label": "Gemini 1.5 Pro",
            "supports_tools": True,
        },
        {
            "id": "gemini-1.5-flash",
            "context": 1_000_000,
            "label": "Gemini 1.5 Flash",
            "supports_tools": True,
        },
    ],
    Provider.OPENAI: [
        {
            "id": "gpt-4o",
            "context": 128_000,
            "label": "GPT-4o (OpenAI)",
            "supports_tools": True,
        },
        {
            "id": "gpt-4o-mini",
            "context": 128_000,
            "label": "GPT-4o mini (OpenAI)",
            "supports_tools": True,
        },
    ],
    Provider.XAI: [
        {
            "id": "grok-3",
            "context": 131_072,
            "label": "Grok-3 (xAI)",
            "supports_tools": True,
        },
        {
            "id": "grok-3-mini",
            "context": 131_072,
            "label": "Grok-3 Mini (xAI)",
            "supports_tools": True,
        },
        {
            "id": "grok-2-1212",
            "context": 131_072,
            "label": "Grok-2 (xAI)",
            "supports_tools": True,
        },
    ],
    Provider.ANTHROPIC: [
        {
            "id": "claude-sonnet-4-6",
            "context": 200_000,
            "label": "Claude Sonnet 4.6 (Anthropic)",
            "supports_tools": True,
        },
        {
            "id": "claude-opus-4-6",
            "context": 200_000,
            "label": "Claude Opus 4.6 (Anthropic)",
            "supports_tools": True,
        },
        {
            "id": "claude-haiku-4-5-20251001",
            "context": 200_000,
            "label": "Claude Haiku 4.5 (Anthropic)",
            "supports_tools": True,
        },
    ],
}

# Erros que disparam fallback imediato
_FALLBACK_ERRORS = {
    "rate_limit_exceeded", "rate limit", "429",
    "insufficient_credits", "insufficient credits",
    "out of credits", "quota exceeded", "quota_exceeded",
    "resource_exhausted", "overloaded",
}


def _is_fallback_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in _FALLBACK_ERRORS)


# ─── Provider state ───────────────────────────────────────────────────────────

@dataclass
class ProviderState:
    provider: Provider
    available: bool = True
    fail_count: int = 0
    last_fail_at: float = 0.0
    cooldown_s: float = 60.0   # back-off antes de tentar de novo

    def mark_fail(self) -> None:
        self.fail_count += 1
        self.last_fail_at = time.monotonic()
        if self.fail_count >= 3:
            self.available = False
            logger.warning(f"[router] {self.provider} marcado como indisponível após {self.fail_count} falhas")

    def mark_ok(self) -> None:
        self.fail_count = 0
        self.available = True

    def is_ready(self) -> bool:
        if self.available:
            return True
        # Tentar reabilitar após cooldown
        if time.monotonic() - self.last_fail_at > self.cooldown_s:
            self.available = True
            self.fail_count = 0
            return True
        return False


# ─── Router principal ─────────────────────────────────────────────────────────

class LunaLLMRouter:
    """
    Roteador multi-LLM com fallback automático.

    Uso básico:
        router = LunaLLMRouter()
        response = router.chat(messages=[...], temperature=0.2)

    Uso com streaming:
        for chunk in router.stream(messages=[...]):
            print(chunk, end="", flush=True)

    Uso com tool calls (function calling):
        response = router.chat_with_tools(messages=[...], tools=[...])
    """

    def __init__(self) -> None:
        self._priority: list[Provider] = self._load_priority()
        self._states: dict[Provider, ProviderState] = {
            p: ProviderState(p) for p in Provider
        }
        self._clients: dict[Provider, object] = {}
        self._current: Provider | None = None
        self._init_clients()

    # ── Configuração ──────────────────────────────────────────────────────

    def _load_priority(self) -> list[Provider]:
        raw = os.getenv("LUNA_LLM_PRIORITY", "together,groq,ollama,gemini,openai")
        order = []
        for name in raw.split(","):
            name = name.strip().lower()
            try:
                order.append(Provider(name))
            except ValueError:
                logger.warning(f"[router] Provedor desconhecido na prioridade: {name}")
        return order or [
            Provider.TOGETHER, Provider.GROQ, Provider.OLLAMA,
            Provider.GEMINI, Provider.OPENAI,
        ]

    def _init_clients(self) -> None:
        """Inicializa clientes lazy — só importa se a key existir."""

        # Together AI
        key = os.getenv("TOGETHER_API_KEY", "").strip()
        if key:
            try:
                from openai import OpenAI
                self._clients[Provider.TOGETHER] = OpenAI(
                    api_key=key,
                    base_url="https://api.together.xyz/v1",
                )
                logger.info("[router] Together AI: cliente inicializado")
            except Exception as e:
                logger.warning(f"[router] Together AI init error: {e}")

        # Groq
        key = os.getenv("GROQ_API_KEY", "").strip()
        if key:
            try:
                from openai import OpenAI
                self._clients[Provider.GROQ] = OpenAI(
                    api_key=key,
                    base_url="https://api.groq.com/openai/v1",
                )
                logger.info("[router] Groq: cliente inicializado")
            except Exception as e:
                logger.warning(f"[router] Groq init error: {e}")

        # Ollama (sem API key — local)
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/v1")
        try:
            from openai import OpenAI
            self._clients[Provider.OLLAMA] = OpenAI(
                api_key="ollama",   # placeholder
                base_url=ollama_url,
            )
            logger.info(f"[router] Ollama: cliente configurado em {ollama_url}")
        except Exception as e:
            logger.warning(f"[router] Ollama init error: {e}")

        # Gemini (via OpenAI-compat endpoint)
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if key:
            try:
                from openai import OpenAI
                self._clients[Provider.GEMINI] = OpenAI(
                    api_key=key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                )
                logger.info("[router] Gemini: cliente inicializado (OpenAI compat)")
            except Exception as e:
                logger.warning(f"[router] Gemini init error: {e}")

        # OpenAI (fallback final)
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if key:
            try:
                from openai import OpenAI
                self._clients[Provider.OPENAI] = OpenAI(api_key=key)
                logger.info("[router] OpenAI: cliente inicializado")
            except Exception as e:
                logger.warning(f"[router] OpenAI init error: {e}")

        # xAI — Grok (OpenAI-compatible endpoint)
        key = os.getenv("XAI_API_KEY", os.getenv("GROK_API_KEY", "")).strip()
        if key:
            try:
                from openai import OpenAI
                self._clients[Provider.XAI] = OpenAI(
                    api_key=key,
                    base_url="https://api.x.ai/v1",
                )
                logger.info("[router] xAI (Grok): cliente inicializado")
            except Exception as e:
                logger.warning(f"[router] xAI init error: {e}")

        # Anthropic — Claude (SDK nativo, não OpenAI-compat)
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if key:
            try:
                import anthropic as _anthropic
                self._clients[Provider.ANTHROPIC] = _anthropic.Anthropic(api_key=key)
                logger.info("[router] Anthropic (Claude): cliente inicializado")
            except ImportError:
                logger.warning("[router] Anthropic SDK não instalado — rode: pip install anthropic")
            except Exception as e:
                logger.warning(f"[router] Anthropic init error: {e}")

    # ── Helpers Anthropic ─────────────────────────────────────────────────

    def _anthropic_chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> str:
        """Chama Anthropic nativo e retorna texto."""
        client = self._clients[Provider.ANTHROPIC]
        # Separa system prompt das demais mensagens
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        chat_msgs = [m for m in messages if m["role"] != "system"]
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=chat_msgs,
        )
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)
        resp = client.messages.create(**kwargs)  # type: ignore[attr-defined]
        return resp.content[0].text if resp.content else ""

    def _anthropic_stream(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> Iterator[str]:
        """Streaming Anthropic nativo."""
        client = self._clients[Provider.ANTHROPIC]
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        chat_msgs = [m for m in messages if m["role"] != "system"]
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=chat_msgs,
        )
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)
        with client.messages.stream(**kwargs) as stream:  # type: ignore[attr-defined]
            for text in stream.text_stream:
                yield text

    def _anthropic_chat_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> object:
        """Tool calling via Anthropic nativo. Retorna o objeto message."""
        client = self._clients[Provider.ANTHROPIC]
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        chat_msgs = [m for m in messages if m["role"] != "system"]
        # Converte tools do formato OpenAI para Anthropic
        ant_tools = []
        for t in tools:
            fn = t.get("function", t)
            ant_tools.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=chat_msgs,
            tools=ant_tools,
        )
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)
        return client.messages.create(**kwargs)  # type: ignore[attr-defined]

    # ── Seleção de provedor ───────────────────────────────────────────────

    def _get_model(self, provider: Provider, needs_tools: bool = False) -> str | None:
        models = PROVIDER_MODELS.get(provider, [])
        for m in models:
            if needs_tools and not m.get("supports_tools", False):
                continue
            return m["id"]
        # Fallback: primeiro modelo mesmo sem tools
        return models[0]["id"] if models else None

    def _next_provider(self, needs_tools: bool = False) -> Provider | None:
        for p in self._priority:
            state = self._states[p]
            if not state.is_ready():
                continue
            if p not in self._clients:
                continue
            model = self._get_model(p, needs_tools)
            if model is None:
                continue
            return p
        return None

    # ── Chat (síncrono) ───────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ) -> str:
        """
        Chama o LLM com fallback automático.
        Retorna o texto da resposta ou raise RuntimeError se todos falharem.
        """
        for attempt in range(len(self._priority) + 1):
            provider = self._next_provider(needs_tools=False)
            if provider is None:
                raise RuntimeError("[router] Todos os provedores esgotados ou indisponíveis.")

            client = self._clients[provider]
            model  = self._get_model(provider, needs_tools=False)
            t0 = time.monotonic()

            try:
                logger.debug(f"[router] Tentando {provider}/{model} (attempt {attempt+1})")

                if provider == Provider.ANTHROPIC:
                    text = self._anthropic_chat(model, messages, temperature, max_tokens, timeout)
                else:
                    resp = client.chat.completions.create(  # type: ignore[attr-defined]
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                    )
                    text = resp.choices[0].message.content or ""

                elapsed = time.monotonic() - t0
                logger.info(f"[router] {provider}/{model} OK em {elapsed:.2f}s")
                self._states[provider].mark_ok()
                self._current = provider
                return text

            except Exception as e:
                elapsed = time.monotonic() - t0
                is_fb = _is_fallback_error(e)
                logger.warning(
                    f"[router] {provider} falhou em {elapsed:.2f}s "
                    f"({'fallback' if is_fb else 'erro'}): {e}"
                )
                self._states[provider].mark_fail()
                # Continua para próximo provedor

        raise RuntimeError("[router] Todos os provedores falharam.")

    # ── Chat com Tools ────────────────────────────────────────────────────

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ) -> object:
        """
        Chama com function calling. Retorna o objeto choice completo.
        Providers sem suporte a tools pulam para o próximo com suporte.
        """
        for attempt in range(len(self._priority) + 1):
            provider = self._next_provider(needs_tools=True)
            if provider is None:
                # Último recurso: tentar sem tools em Ollama local
                provider = self._next_provider(needs_tools=False)
                if provider is None:
                    raise RuntimeError("[router] Nenhum provedor disponível para tool calling.")
                tools = []   # degraded mode

            client = self._clients[provider]
            model  = self._get_model(provider, needs_tools=bool(tools))
            t0 = time.monotonic()

            try:
                if provider == Provider.ANTHROPIC:
                    resp = self._anthropic_chat_with_tools(
                        model, messages, tools or [], temperature, max_tokens
                    )
                else:
                    kwargs: dict = dict(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                    )
                    if tools:
                        kwargs["tools"] = tools
                        kwargs["tool_choice"] = "auto"
                    resp = client.chat.completions.create(**kwargs)  # type: ignore[attr-defined]

                elapsed = time.monotonic() - t0
                logger.info(f"[router] {provider}/{model} (tools) OK em {elapsed:.2f}s")
                self._states[provider].mark_ok()
                self._current = provider
                return resp

            except Exception as e:
                elapsed = time.monotonic() - t0
                logger.warning(f"[router] {provider} (tools) falhou em {elapsed:.2f}s: {e}")
                self._states[provider].mark_fail()

        raise RuntimeError("[router] Tool calling falhou em todos os provedores.")

    # ── Streaming ─────────────────────────────────────────────────────────

    def stream(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> Iterator[str]:
        """
        Streaming com fallback. Yields texto em chunks.
        Se o primeiro provedor falhar antes do primeiro chunk, troca imediatamente.
        """
        for attempt in range(len(self._priority) + 1):
            provider = self._next_provider(needs_tools=False)
            if provider is None:
                raise RuntimeError("[router] Nenhum provedor disponível para streaming.")

            client = self._clients[provider]
            model  = self._get_model(provider, needs_tools=False)
            t0 = time.monotonic()
            got_first_chunk = False

            try:
                if provider == Provider.ANTHROPIC:
                    for text_chunk in self._anthropic_stream(model, messages, temperature, max_tokens):
                        if not got_first_chunk:
                            got_first_chunk = True
                            logger.info(f"[router] {provider}/{model} streaming: primeiro chunk em {time.monotonic()-t0:.2f}s")
                        yield text_chunk
                else:
                    stream = client.chat.completions.create(  # type: ignore[attr-defined]
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        timeout=timeout,
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content if chunk.choices else None
                        if delta:
                            if not got_first_chunk:
                                got_first_chunk = True
                                logger.info(f"[router] {provider}/{model} streaming: primeiro chunk em {time.monotonic()-t0:.2f}s")
                            yield delta

                self._states[provider].mark_ok()
                self._current = provider
                return  # sucesso — encerra o generator

            except Exception as e:
                elapsed = time.monotonic() - t0
                if got_first_chunk:
                    # Já começou a transmitir — não pode trocar de provedor no meio
                    logger.error(f"[router] {provider} falhou durante streaming ({elapsed:.2f}s): {e}")
                    return
                logger.warning(f"[router] {provider} falhou antes do primeiro chunk ({elapsed:.2f}s): {e}")
                self._states[provider].mark_fail()
                # Tenta próximo provedor

    # ── Utilitários ───────────────────────────────────────────────────────

    def status(self) -> dict:
        """Retorna o estado atual de todos os provedores (formato rico para /router CLI)."""
        providers_list = []
        for p in self._priority:
            state = self._states[p]
            models = PROVIDER_MODELS.get(p, [])
            ctx = models[0]["context"] if models else 0
            state_str = "ok" if state.is_ready() else "cooldown"
            providers_list.append({
                "name":          p.value,
                "model":         models[0]["label"] if models else "-",
                "state":         state_str,
                "failures":      state.fail_count,
                "has_client":    p in self._clients,
                "context_limit": ctx,
            })
        # active_provider = primeiro pronto com cliente
        active = None
        for p in self._priority:
            if self._states[p].is_ready() and p in self._clients:
                active = p.value
                break
        return {
            "active_provider":  active or "none",
            "context_limit":    self.get_context_limit(),
            "providers":        providers_list,
        }

    def reset(self, provider: Provider | None = None) -> None:
        """Reseta estado de falha de um ou todos os provedores."""
        targets = [provider] if provider else list(Provider)
        for p in targets:
            if p in self._states:
                self._states[p].mark_ok()

    def get_context_limit(self) -> int:
        """Retorna o limite de contexto do provedor atual ativo."""
        for p in self._priority:
            if self._states[p].is_ready() and p in self._clients:
                models = PROVIDER_MODELS.get(p, [])
                if models:
                    return models[0]["context"]
        return 8192  # fallback conservador

    @property
    def current_provider(self) -> str:
        return self._current.value if self._current else "nenhum"


# ─── Tiered Reasoning ────────────────────────────────────────────────────────

# Modelos específicos por tier
_TIER0_PROVIDER = Provider.GROQ
_TIER0_MODEL    = "llama-3-8b-instant"       # custo ≈ zero (Groq free tier)
_TIER1_PROVIDER = Provider.TOGETHER
_TIER1_MODEL    = "meta-llama/Llama-3.1-405B-Instruct-Turbo"   # deep audit
_TIER1_MODEL_CODE = "deepseek-ai/DeepSeek-V2.5"                 # alternativa código


class TieredReasoning:
    """
    Hierarquia de raciocínio para otimizar custo x qualidade.

    Tier 0 (Free/Triage): Groq Llama-3-8B — escanamento rápido, custo zero.
    Tier 1 (Deep Audit):  Together AI Llama-3.1-405B — análise lógica profunda.
    Tier 2 (Code):        DeepSeek-Coder-V2 — raciocínio específico de código.

    Retorna: (texto_resposta, input_tokens, output_tokens)
    """

    def __init__(self, router: LunaLLMRouter) -> None:
        self._router = router

    def _call(
        self,
        provider: Provider,
        model_id: str,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> tuple[str, int, int]:
        """Chama um provider/model específico. Retorna (text, input_tokens, output_tokens)."""
        if provider not in self._router._clients:
            raise RuntimeError(
                f"Provider {provider.value} não configurado. "
                f"Defina a API key no .env ({provider.value.upper()}_API_KEY)"
            )

        client = self._router._clients[provider]
        t0 = time.monotonic()

        resp = client.chat.completions.create(  # type: ignore[attr-defined]
            model=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=120.0,
        )

        text = resp.choices[0].message.content or ""
        usage = resp.usage
        input_tokens  = usage.prompt_tokens     if usage else len(str(messages)) // 4
        output_tokens = usage.completion_tokens if usage else len(text) // 4

        elapsed = time.monotonic() - t0
        logger.info(
            f"[tiered] {provider.value}/{model_id.split('/')[-1]} "
            f"OK in {elapsed:.2f}s  tokens={input_tokens}+{output_tokens}"
        )
        self._router._states[provider].mark_ok()
        return text, input_tokens, output_tokens

    def triage(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 1500,
    ) -> tuple[str, int, int]:
        """
        Tier 0: Triage rápido com Groq Llama-3-8B.
        Se Groq indisponível, usa Groq Llama-3.1-70B ou router normal.
        """
        # Tentar Groq 8B primeiro
        groq_models = [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
        ]
        if Provider.GROQ in self._router._clients and self._router._states[Provider.GROQ].is_ready():
            for model_id in groq_models:
                try:
                    return self._call(Provider.GROQ, model_id, messages, temperature, max_tokens)
                except Exception as e:
                    logger.debug(f"[tiered] Groq {model_id} falhou: {e}")

        # Fallback: usar router normal (menor custo disponível)
        logger.info("[tiered] Groq 8B não disponível — usando router padrão para triage")
        text = self._router.chat(messages, temperature=temperature, max_tokens=max_tokens)
        est_tokens = len(str(messages)) // 4
        return text, est_tokens, len(text) // 4

    def deep_audit(
        self,
        messages: list[dict],
        temperature: float = 0.15,
        max_tokens: int = 8000,
    ) -> tuple[str, int, int]:
        """
        Tier 1: Análise profunda com Together AI Llama-3.1-405B.
        Fallback: DeepSeek-Coder ou router padrão.
        """
        together_models = [
            "meta-llama/Llama-3.1-405B-Instruct-Turbo",
            "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
            "meta-llama/Llama-3.1-70B-Instruct-Turbo",
        ]
        if Provider.TOGETHER in self._router._clients and self._router._states[Provider.TOGETHER].is_ready():
            for model_id in together_models:
                try:
                    return self._call(Provider.TOGETHER, model_id, messages, temperature, max_tokens)
                except Exception as e:
                    logger.warning(f"[tiered] Together {model_id} falhou: {e}")

        # Fallback: Groq 70B
        if Provider.GROQ in self._router._clients and self._router._states[Provider.GROQ].is_ready():
            try:
                return self._call(Provider.GROQ, "llama-3.3-70b-versatile", messages, temperature, max_tokens)
            except Exception as e:
                logger.warning(f"[tiered] Groq 70B falhou: {e}")

        # Último recurso: router padrão
        logger.warning("[tiered] Together não disponível — usando router padrão para deep audit")
        text = self._router.chat(messages, temperature=temperature, max_tokens=max_tokens)
        est_tokens = len(str(messages)) // 4
        return text, est_tokens, len(text) // 4

    def code_analysis(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> tuple[str, int, int]:
        """
        Tier 2: Análise de código com DeepSeek-Coder via Together AI.
        Fallback: Together AI 405B.
        """
        code_models = [
            ("together", "deepseek-ai/DeepSeek-V2.5"),
            ("together", "deepseek-ai/deepseek-coder-v2-instruct"),
        ]
        if Provider.TOGETHER in self._router._clients:
            for _, model_id in code_models:
                try:
                    return self._call(Provider.TOGETHER, model_id, messages, temperature, max_tokens)
                except Exception:
                    pass

        # Fallback para deep_audit padrão
        return self.deep_audit(messages, temperature, max_tokens)


# ─── Singleton global ─────────────────────────────────────────────────────────

_router: LunaLLMRouter | None = None


def get_router() -> LunaLLMRouter:
    global _router
    if _router is None:
        _router = LunaLLMRouter()
    return _router


def reset_router() -> None:
    global _router
    _router = None
