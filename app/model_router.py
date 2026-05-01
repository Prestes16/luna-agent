"""
Luna Agent - Roteador de Modelos (Multi-Model)
Seleção inteligente de modelos baseada em custo, latência e disponibilidade.
"""

from __future__ import annotations

import os
import logging
from typing import Optional, Any
from enum import Enum

from app.models import ModelProvider, AgentConfig


logger = logging.getLogger("luna.model_router")


# ─────────────────────────────────────────────────────────────────────────
# Configuração de Modelos
# ─────────────────────────────────────────────────────────────────────────

class ModelConfig:
    """Configuração de um modelo."""
    
    def __init__(
        self,
        provider: ModelProvider,
        model_id: str,
        cost_per_1k_input: float,
        cost_per_1k_output: float,
        max_tokens: int = 8192,
        latency_ms: float = 100.0,
        available: bool = True,
    ):
        self.provider = provider
        self.model_id = model_id
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output
        self.max_tokens = max_tokens
        self.latency_ms = latency_ms
        self.available = available


# Modelos disponíveis
AVAILABLE_MODELS: dict[ModelProvider, list[ModelConfig]] = {
    "openai": [
        ModelConfig("openai", "gpt-4o", 0.015, 0.06, 128000, 150.0),
        ModelConfig("openai", "gpt-4-turbo", 0.01, 0.03, 128000, 200.0),
        ModelConfig("openai", "gpt-4", 0.03, 0.06, 8192, 250.0),
    ],
    "gemini": [
        ModelConfig("gemini", "gemini-2.5-flash", 0.075, 0.3, 1000000, 100.0),
        ModelConfig("gemini", "gemini-1.5-pro", 0.0075, 0.03, 1000000, 200.0),
    ],
    "grok": [
        ModelConfig("grok", "grok-2", 0.02, 0.06, 131072, 180.0),
    ],
    "claude": [
        ModelConfig("claude", "claude-3.5-sonnet", 0.003, 0.015, 200000, 150.0),
        ModelConfig("claude", "claude-3-opus", 0.015, 0.075, 200000, 200.0),
    ],
}


# ─────────────────────────────────────────────────────────────────────────
# Roteador de Modelos
# ─────────────────────────────────────────────────────────────────────────

class ModelRouter:
    """Roteador inteligente de modelos."""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.primary_model = config.primary_model
        self.fallback_models = config.fallback_models
        self.strategy = config.model_routing_strategy
        self._model_cache: dict[str, Any] = {}
    
    def select_model(
        self,
        task_type: str = "general",
        prefer_speed: bool = False,
        prefer_cost: bool = True,
    ) -> tuple[ModelProvider, str]:
        """
        Selecionar o melhor modelo para uma tarefa.
        
        Args:
            task_type: Tipo de tarefa (general, code, analysis, etc.)
            prefer_speed: Priorizar latência baixa
            prefer_cost: Priorizar custo baixo
            
        Returns:
            Tupla (provider, model_id)
        """
        
        # Estratégia 1: Round-robin (alternância simples)
        if self.strategy == "round_robin":
            return self._select_round_robin()
        
        # Estratégia 2: Consciente de custo (padrão)
        if self.strategy == "cost_aware":
            return self._select_cost_aware(prefer_speed)
        
        # Estratégia 3: Consciente de latência
        if self.strategy == "latency_aware":
            return self._select_latency_aware(prefer_cost)
        
        # Fallback
        return self.primary_model, self._get_default_model_id(self.primary_model)
    
    def _select_round_robin(self) -> tuple[ModelProvider, str]:
        """Selecionar modelo por round-robin."""
        models = [self.primary_model] + self.fallback_models
        
        for provider in models:
            if provider in AVAILABLE_MODELS:
                configs = AVAILABLE_MODELS[provider]
                if configs:
                    return provider, configs[0].model_id
        
        return "openai", "gpt-4o"
    
    def _select_cost_aware(self, prefer_speed: bool = False) -> tuple[ModelProvider, str]:
        """Selecionar modelo consciente de custo."""
        best_provider = None
        best_model = None
        best_score = float("inf")
        
        for provider in [self.primary_model] + self.fallback_models:
            if provider not in AVAILABLE_MODELS:
                continue
            
            for model_config in AVAILABLE_MODELS[provider]:
                if not model_config.available:
                    continue
                
                # Calcular score: custo médio + latência (se prefer_speed)
                avg_cost = (model_config.cost_per_1k_input + model_config.cost_per_1k_output) / 2
                score = avg_cost
                
                if prefer_speed:
                    score += model_config.latency_ms / 1000.0
                
                if score < best_score:
                    best_score = score
                    best_provider = provider
                    best_model = model_config.model_id
        
        return best_provider or "openai", best_model or "gpt-4o"
    
    def _select_latency_aware(self, prefer_cost: bool = False) -> tuple[ModelProvider, str]:
        """Selecionar modelo consciente de latência."""
        best_provider = None
        best_model = None
        best_score = float("inf")
        
        for provider in [self.primary_model] + self.fallback_models:
            if provider not in AVAILABLE_MODELS:
                continue
            
            for model_config in AVAILABLE_MODELS[provider]:
                if not model_config.available:
                    continue
                
                # Calcular score: latência + custo (se prefer_cost)
                score = model_config.latency_ms
                
                if prefer_cost:
                    avg_cost = (model_config.cost_per_1k_input + model_config.cost_per_1k_output) / 2
                    score += avg_cost * 1000.0  # Normalizar para escala de latência
                
                if score < best_score:
                    best_score = score
                    best_provider = provider
                    best_model = model_config.model_id
        
        return best_provider or "openai", best_model or "gpt-4o"
    
    def _get_default_model_id(self, provider: ModelProvider) -> str:
        """Obter model_id padrão para um provider."""
        if provider in AVAILABLE_MODELS and AVAILABLE_MODELS[provider]:
            return AVAILABLE_MODELS[provider][0].model_id
        return "gpt-4o"
    
    def get_client(self, provider: ModelProvider) -> Any:
        """Obter cliente para um provider."""
        
        # Verificar cache
        cache_key = f"client_{provider}"
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]
        
        # Criar cliente baseado no provider
        if provider == "openai":
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise ValueError("OPENAI_API_KEY não configurada")
            client = OpenAI(api_key=api_key)
        
        elif provider == "gemini":
            from google import genai as genai_client
            api_key = os.getenv("GOOGLE_API_KEY", "").strip()
            if not api_key:
                raise ValueError("GOOGLE_API_KEY não configurada")
            client = genai_client.Client(api_key=api_key)
        
        elif provider == "grok":
            from openai import OpenAI
            api_key = os.getenv("XAI_API_KEY", "").strip()
            if not api_key:
                raise ValueError("XAI_API_KEY não configurada")
            client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        
        elif provider == "claude":
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY não configurada")
            client = anthropic.Anthropic(api_key=api_key)
        
        else:
            raise ValueError(f"Provider desconhecido: {provider}")
        
        self._model_cache[cache_key] = client
        return client
    
    def call_model(
        self,
        messages: list[dict],
        model_provider: Optional[ModelProvider] = None,
        model_id: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> str:
        """
        Chamar um modelo com fallback automático.
        
        Args:
            messages: Lista de mensagens
            model_provider: Provider preferido (None = usar roteador)
            model_id: Model ID preferido
            temperature: Temperatura de sampling
            max_tokens: Máximo de tokens na resposta
            
        Returns:
            Texto da resposta
        """
        
        # Selecionar modelo se não especificado
        if not model_provider:
            model_provider, model_id = self.select_model()
        
        if not model_id:
            model_id = self._get_default_model_id(model_provider)
        
        try:
            return self._call_model_internal(
                model_provider, model_id, messages, temperature, max_tokens, **kwargs
            )
        except Exception as e:
            logger.warning(f"Erro ao chamar {model_provider}/{model_id}: {e}")
            
            # Tentar fallback
            for fallback_provider in self.fallback_models:
                if fallback_provider == model_provider:
                    continue
                
                try:
                    fallback_id = self._get_default_model_id(fallback_provider)
                    logger.info(f"Tentando fallback: {fallback_provider}/{fallback_id}")
                    return self._call_model_internal(
                        fallback_provider, fallback_id, messages, temperature, max_tokens, **kwargs
                    )
                except Exception as e2:
                    logger.warning(f"Fallback {fallback_provider} também falhou: {e2}")
                    continue
            
            raise RuntimeError(f"Todos os modelos falharam. Último erro: {e}")
    
    def _call_model_internal(
        self,
        provider: ModelProvider,
        model_id: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> str:
        """Implementação interna de chamada de modelo."""
        
        if provider == "openai":
            client = self.get_client(provider)
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return response.choices[0].message.content or ""
        
        elif provider == "gemini":
            client = self.get_client(provider)
            # Montar conteúdo: usar todas as mensagens no formato google-genai
            contents = []
            for msg in messages:
                role = "user" if msg["role"] != "assistant" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            response = client.models.generate_content(
                model=model_id,
                contents=contents,
                config={"temperature": temperature, "max_output_tokens": max_tokens},
            )
            return response.text or ""
        
        elif provider == "grok":
            client = self.get_client(provider)
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return response.choices[0].message.content or ""
        
        elif provider == "claude":
            client = self.get_client(provider)
            response = client.messages.create(
                model=model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return response.content[0].text if response.content else ""
        
        else:
            raise ValueError(f"Provider desconhecido: {provider}")
