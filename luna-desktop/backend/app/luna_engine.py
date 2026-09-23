"""
Luna Engine - Elite Multi-Model AI Agent
Supports: OpenAI, Anthropic, Groq (Llama), xAI (Grok), Together AI
Auto-routing + tool-calling loop (filesystem + web access).
"""

import os
import json
import logging
import asyncio
import re
import socket
import time
from typing import Optional, List, Dict, Any, AsyncIterator
from datetime import datetime

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

from .models import ChatResponse, ModelProvider, ChatRequest, MemoryEntry
from .module_loader import ModuleLoader
from .construction_reasoning import construction_guidance
from .decision_intelligence import decision_guidance
from .host_safety import host_safety_guidance
from .kali_tool_guidance import guidance_for_context
from .malware_analysis import malware_guidance, malware_tooling_summary
from .technical_capabilities import technical_guidance
from .threat_response import threat_response_guidance
from .reasoning_pipeline import (
    build_replan_instruction,
    classify_complexity,
    redact_sensitive_text,
    validate_model_response,
)
from .scenario_context import ScenarioContext
from .tools import (
    TOOL_DEFINITIONS, TOOL_DEFINITIONS_CLAUDE, execute_tool,
)

logger = logging.getLogger(__name__)

# ── Ollama local endpoint ─────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_ROOT = OLLAMA_BASE_URL.removesuffix("/v1").rstrip("/")

# This build is deliberately instruction-only. The model may generate commands,
# code and configuration for the operator, but it never receives host-execution
# tools. Changing this behavior requires a deliberate code change and new tests.
INSTRUCTION_ONLY_BUILD = True

# Modelos Ollama recomendados — usuário precisa ter feito `ollama pull <model>`
_OLLAMA_DEFAULT_MODEL = "luna-cyber-fast"
_OLLAMA_FALLBACK_MODEL = "qwen3.5:4b"
_OLLAMA_ALT_MODELS = [_OLLAMA_FALLBACK_MODEL]
_OLLAMA_MODELS_CACHE: tuple[float, List[str]] = (0.0, [])
_OLLAMA_MODELS_CACHE_TTL_SECONDS = 30.0

# ── Model routing map ─────────────────────────────────────────────────────────
MODEL_MAP: Dict[str, tuple] = {
    # Cloud — OpenAI
    'gpt-4o':                ('openai',   'gpt-4o'),
    'gpt-4o-mini':           ('openai',   'gpt-4o-mini'),
    'gpt-4-turbo':           ('openai',   'gpt-4-turbo'),
    'gpt-4':                 ('openai',   'gpt-4'),
    # Cloud — Anthropic
    'claude-3-7':            ('claude',   'claude-3-7-sonnet-20250219'),
    'claude-3-5-sonnet':     ('claude',   'claude-3-5-sonnet-20241022'),
    'claude-3-5-haiku':      ('claude',   'claude-3-5-haiku-20241022'),
    # Cloud — xAI / Groq / Together
    'grok-2':                ('xai',      'grok-2-latest'),
    'grok-beta':             ('xai',      'grok-beta'),
    'llama-3.1-70b':         ('groq',     'llama-3.1-70b-versatile'),
    'llama-3.3-70b':         ('groq',     'llama-3.3-70b-versatile'),
    'llama-3.1-8b':          ('groq',     'llama-3.1-8b-instant'),
    'llama-3.1-405b':        ('together', 'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo'),
    'meta-llama/405B':       ('together', 'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo'),
    # Local — Ollama (zero-cloud)
    'luna-cyber-fast':       ('ollama',   _OLLAMA_DEFAULT_MODEL),
    'ollama':                ('ollama',   _OLLAMA_DEFAULT_MODEL),
    'ollama:auto':           ('ollama',   _OLLAMA_DEFAULT_MODEL),
    'ollama:luna-cyber-fast': ('ollama',  _OLLAMA_DEFAULT_MODEL),
    'ollama:qwen3.5:4b':     ('ollama',   _OLLAMA_FALLBACK_MODEL),
    'ollama:llama3.3:70b':   ('ollama',   'llama3.3:70b'),
    'ollama:llama3.1:70b':   ('ollama',   'llama3.1:70b'),
    'ollama:llama3.1:8b':    ('ollama',   'llama3.1:8b'),
    'ollama:qwen2.5:72b':    ('ollama',   'qwen2.5:72b'),
    'ollama:mistral':        ('ollama',   'mistral:latest'),
    'ollama:phi4':           ('ollama',   'phi4'),
    'ollama:deepseek-r1':    ('ollama',   'deepseek-r1:latest'),
    # Auto-roteamento
    'auto':                  ('auto',     None),
}


# ── Ollama availability helpers ───────────────────────────────────────────────

def _ollama_is_available_sync() -> bool:
    """Verifica (síncronamente) se o Ollama está rodando em localhost:11434."""
    try:
        s = socket.create_connection(("localhost", 11434), timeout=1.0)
        s.close()
        return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


async def _ollama_list_models_async(*, force: bool = False) -> List[str]:
    """
    Retorna lista de modelos disponíveis no Ollama local.
    Usa httpx de forma assíncrona. Retorna [] se Ollama não está rodando.
    """
    global _OLLAMA_MODELS_CACHE
    cached_at, cached_models = _OLLAMA_MODELS_CACHE
    if not force and cached_models and time.monotonic() - cached_at < _OLLAMA_MODELS_CACHE_TTL_SECONDS:
        return list(cached_models)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{OLLAMA_API_ROOT}/api/tags")
            if r.status_code == 200:
                data = r.json()
                models = [m["name"] for m in data.get("models", [])]
                _OLLAMA_MODELS_CACHE = (time.monotonic(), models)
                return list(models)
    except Exception:
        pass
    return []


async def _ollama_best_model_async(preferred: str = _OLLAMA_DEFAULT_MODEL) -> str:
    """
    Retorna o melhor modelo Ollama disponível.
    Tenta 'preferred' primeiro, depois percorre _OLLAMA_ALT_MODELS.
    """
    available = await _ollama_list_models_async()
    if not available:
        return preferred  # vai falhar na chamada — o erro vai ser tratado no fallback

    def _matches(model: str) -> Optional[str]:
        if model in available:
            return model
        if ":" not in model:
            tagged = f"{model}:latest"
            if tagged in available:
                return tagged
        return None

    for candidate in [preferred] + _OLLAMA_ALT_MODELS:
        match = _matches(candidate)
        if match:
            return match

    # Do not silently select an arbitrary or oversized local model.
    return preferred


def _check_internet() -> bool:
    """Verifica conectividade básica com a internet (DNS + TCP)."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2.0).close()
        return True
    except OSError:
        return False


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


_SEC_KEYWORDS = [
    'vulnerability', 'vulnerabilidade', 'exploit', 'xss', 'injection', 'overflow',
    'reentrancy', 'reentrância', 'audit', 'auditoria', 'pentest', 'bounty',
    'solana', 'anchor', 'smart contract', 'program', 'hack', 'attack', 'bypass',
    'privilege escalation', 'race condition', 'memory corruption', 'cve', 'poc',
]
_CODE_KEYWORDS = [
    'implement', 'implemente', 'build', 'construa', 'create', 'crie', 'architect',
    'refactor', 'refatore', 'optimize', 'otimize', 'debug', 'analyze', 'analise',
]
def _build_system_prompt(
    workspace_path: Optional[str],
    context_summary: Optional[str] = None,
    user_context: Optional[str] = None,
    scenario_context: Optional[str] = None,
    evidence_delta: Optional[str] = None,
    route_instruction: Optional[str] = None,
    project_context: Optional[str] = None,
    active_modules: Optional[Dict[str, str]] = None,
    supervised_mode: bool = True,
) -> str:
    """Build only the small, session-specific context missing from the Modelfile."""

    lines = [
        "CONTEXTO DINÂMICO DE RUNTIME",
        f"Data/hora local: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        (
            "Modo de operação: copiloto supervisionado; o operador executa comandos."
            if supervised_mode
            else "Modo de operação: ferramentas restritas habilitadas."
        ),
        (
            "Regra contextual: cenário -> fatos -> desconhecidos -> pergunta atual -> "
            "teste mínimo. Nunca promova desconhecidos a fatos."
        ),
        (
            "Princípio BUILD-TO-BREAK: antes de quebrar, explorar ou auditar, reconstrua o modelo "
            "mínimo de como o componente funciona: interfaces, fluxos, estado, fronteiras de "
            "confiança, invariantes, dependências e controles. Se esse modelo estiver incompleto, "
            "priorize evidência estrutural antes de assumir o mecanismo da falha."
        ),
        (
            "Prioridade: CURRENT USER MESSAGE > evidence delta > ScenarioContext > "
            "project context > memory summary > mensagens antigas da assistente."
        ),
        (
            "Exemplos pre-carregados no modelo ou em módulos são somente estilo/instrução, "
            "nunca fatos do cenário. Não importe endpoint, header ou resultado que não esteja "
            "na evidência atual."
        ),
        (
            "Qualquer endpoint/header fora das allowlists factuais ou da mensagem atual é "
            "alucinação e não pode aparecer nem como histórico."
        ),
        (
            "Comandos Bash/Kali devem usar executáveis e flags reais. Preserve literalmente a "
            "ferramenta e o target do operador; não invente nomes de produto, host, porta ou path."
        ),
        (
            "Para Nmap inicial no Kali, prefira técnica explícita: -sS quando raw sockets/sudo "
            "forem adequados; -sT quando a execução precisar ser não privilegiada. Não use -A "
            "nem --script=vuln por padrão sem pedido correspondente."
        ),
        (
            "Arquivos de saída são opt-in: não acrescente -oN/-oA/.txt/.xml nem caminho de "
            "artefato se o operador não pediu explicitamente persistência."
        ),
        (
            "Administração de comandos: DISCOVER/PREFLIGHT -> PLAN -> EXECUTE -> VERIFY -> "
            "ROLLBACK/CONTINUE. Execute ou proponha somente uma mudança de estado por vez; "
            "não encadeie mutações ainda não verificadas. Diferencie ação somente-leitura, "
            "mudança transitória, mudança persistente, privilégio e comando interativo. "
            "Mudança persistente/privilegiada exige confirmação explícita e rollback factual."
        ),
        (
            "Proteção do host: para qualquer comando capaz de alterar disco/partição/boot, árvore "
            "de sistema, firewall/rota, persistência ou configuração global, comece por diagnóstico "
            "somente-leitura. Nunca use download remoto encadeado diretamente a shell. Não proponha "
            "alteração crítica sem ambiente factual, snapshot/backup confirmado quando aplicável, "
            "escopo mínimo, verificação pós-estado e rollback."
        ),
        (
            "Se o operador pedir somente um comando, entregue o comando executável de forma "
            "direta; explicações extras devem ser mínimas e tecnicamente necessárias."
        ),
        "Entregue somente a resposta final; nunca exponha chain-of-thought.",
    ]

    if route_instruction:
        lines.extend(("", route_instruction[:1_600]))

    if evidence_delta:
        lines.extend(("", evidence_delta[:800]))

    if workspace_path:
        lines.append(f"Workspace informado (somente contexto): {workspace_path}")

    if user_context:
        lines.extend(("", "Contexto ativo informado pelo usuário:", redact_sensitive_text(user_context)[:350]))

    if project_context:
        lines.extend(("", "Contexto local do projeto:", redact_sensitive_text(project_context)[:500]))

    if scenario_context:
        lines.extend(("", scenario_context[:700]))

    if context_summary:
        lines.extend(("", "Resumo comprimido da sessão:", redact_sensitive_text(context_summary)[:450]))

    for module_id, module_content in (active_modules or {}).items():
        lines.extend(
            (
                "",
                f"Módulo ativo: {module_id}",
                module_content[:650],
            )
        )

    return "\n".join(lines).strip()

class LunaEngine:
    """Luna's core multi-model AI engine with tool-calling loop."""

    MAX_TOOL_ITERATIONS   = 40   # deep project analysis: read 25+ files, full audit loops
    COMPRESS_THRESHOLD    = 8    # messages (4 turns) before compression
    COMPRESS_KEEP_RECENT  = 4    # messages (2 turns) kept verbatim
    COMPRESS_MAX_CHARS    = 8_000

    def __init__(self):
        openai_key   = os.getenv("OPENAI_API_KEY")
        claude_key   = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        groq_key     = os.getenv("GROQ_API_KEY")
        xai_key      = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
        together_key = os.getenv("TOGETHER_API_KEY")

        self.openai_client  = AsyncOpenAI(api_key=openai_key)     if openai_key   else None
        self.claude_client  = AsyncAnthropic(api_key=claude_key)  if claude_key   else None
        self.groq_client    = (
            AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
            if groq_key else None
        )
        self.xai_client     = (
            AsyncOpenAI(api_key=xai_key, base_url="https://api.x.ai/v1")
            if xai_key else None
        )
        self.together_client = (
            AsyncOpenAI(api_key=together_key, base_url="https://api.together.xyz/v1")
            if together_key else None
        )

        # Ollama — sempre disponível se rodando localmente (sem API key)
        self.ollama_client = AsyncOpenAI(
            api_key="ollama",          # Ollama aceita qualquer string
            base_url=OLLAMA_BASE_URL,
        )
        self._ollama_available = _ollama_is_available_sync()
        if self._ollama_available:
            logger.info("Ollama detectado em %s", OLLAMA_BASE_URL)

        self._available_providers = [
            k for k, v in [
                ('OpenAI', openai_key), ('Claude', claude_key),
                ('Groq', groq_key), ('xAI', xai_key), ('Together', together_key),
            ] if v
        ]
        if self._ollama_available:
            self._available_providers.append('Ollama')

        if self._available_providers:
            logger.info("Luna Engine ready - providers: %s", ", ".join(self._available_providers))
        else:
            logger.warning("Ollama não está acessível em localhost:11434.")

        self.histories: Dict[str, List[Dict[str, Any]]] = {}
        self.compression_summaries: Dict[str, str] = {}   # session_id → accumulated summary
        self.scenario_contexts: Dict[str, ScenarioContext] = {}
        self.turn_metadata: Dict[str, Dict[str, Any]] = {}
        # Provedores cujas keys foram confirmadas como inválidas (401) nesta sessão
        self._bad_key_providers: set = set()
        self.config = {
            "default_model": os.getenv("LUNA_MODEL", _OLLAMA_DEFAULT_MODEL),
            "temperature": None,
            "max_tokens": _env_int("LUNA_MAX_TOKENS", 512, 64, 4_096),
            "zero_cloud_mode": _env_flag("LUNA_ZERO_CLOUD", True),
            "mentor_mode": _env_flag("LUNA_MENTOR_MODE", True),
            "reasoning_mode": "FAST",
            "native_reasoning_effort": _env_flag("LUNA_NATIVE_REASONING_EFFORT", False),
            "instruction_only_mode": True,
            "tool_execution_enabled": False,
            "reflection_enabled": False, # Self-Reflection loop (task #15)
        }
        self.module_loader = ModuleLoader()
        self.active_modules = self.module_loader.load_enabled(
            ["mentor_kali_devtools"] if self.config["mentor_mode"] else []
        )

    def _tool_execution_allowed(self) -> bool:
        """Hard invariant for the current build: model tools never execute on the host."""
        return False if INSTRUCTION_ONLY_BUILD else bool(
            self.config.get("tool_execution_enabled", False)
        )

    # ── Client reinitialization (called after API keys update via IPC) ────────

    def _reinit_clients(self) -> None:
        """
        Reinicializa os clientes LLM com as keys atuais do ambiente.
        Chamado pelo endpoint /api/config/keys após o Electron enviar novas keys.
        """
        openai_key   = os.getenv("OPENAI_API_KEY")
        claude_key   = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        groq_key     = os.getenv("GROQ_API_KEY")
        xai_key      = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
        together_key = os.getenv("TOGETHER_API_KEY")

        self.openai_client   = AsyncOpenAI(api_key=openai_key)     if openai_key   else None
        self.claude_client   = AsyncAnthropic(api_key=claude_key)  if claude_key   else None
        self.groq_client     = (
            AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
            if groq_key else None
        )
        self.xai_client      = (
            AsyncOpenAI(api_key=xai_key, base_url="https://api.x.ai/v1")
            if xai_key else None
        )
        self.together_client = (
            AsyncOpenAI(api_key=together_key, base_url="https://api.together.xyz/v1")
            if together_key else None
        )

        # Ollama — reatualiza disponibilidade
        self._ollama_available = _ollama_is_available_sync()

        self._available_providers = [
            k for k, v in [
                ('OpenAI', openai_key), ('Claude', claude_key),
                ('Groq', groq_key), ('xAI', xai_key), ('Together', together_key),
            ] if v
        ]
        if self._ollama_available:
            self._available_providers.append('Ollama')

        logger.info(f"🔄 Clients reinitializados — providers: {', '.join(self._available_providers) or 'nenhum'}")

    # ── Model resolution ──────────────────────────────────────────────────────

    def _resolve_model(self, message: str, model_str: str) -> tuple:
        # Zero-Cloud Mode: força Ollama para TUDO, ignora modelo solicitado
        if self.config.get("zero_cloud_mode"):
            return ('ollama', self.config.get("default_model", _OLLAMA_DEFAULT_MODEL))

        entry = MODEL_MAP.get(model_str)
        if entry is None:
            return self._auto_route(message)
        client_type, model_name = entry
        if client_type == 'auto':
            return self._auto_route(message)
        return client_type, model_name

    def _auto_route(self, message: str) -> tuple:
        msg = message.lower()
        bad = self._bad_key_providers  # provedores com key inválida confirmada

        def ok_openai():   return self.openai_client   and 'openai'   not in bad
        def ok_claude():   return self.claude_client   and 'claude'   not in bad
        def ok_groq():     return self.groq_client     and 'groq'     not in bad
        def ok_together(): return self.together_client and 'together' not in bad
        def ok_xai():      return self.xai_client      and 'xai'      not in bad

        # Zero-Cloud Mode: Ollama primeiro
        if self.config.get("zero_cloud_mode"):
            return ('ollama', self.config.get("default_model", _OLLAMA_DEFAULT_MODEL))

        # Sem internet: forçar Ollama se disponível
        if not _check_internet() and self._ollama_available:
            logger.info("🦙 Sem internet detectada — usando Ollama local")
            return ('ollama', _OLLAMA_DEFAULT_MODEL)

        # Security / blockchain / audit → prefer Claude > OpenAI > Ollama > Together
        if any(k in msg for k in _SEC_KEYWORDS):
            if ok_claude():    return ('claude',   'claude-3-5-sonnet-20241022')
            if ok_openai():    return ('openai',   'gpt-4o')
            if self._ollama_available: return ('ollama', _OLLAMA_DEFAULT_MODEL)
            if ok_together():  return ('together', 'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo')

        # Complex code tasks → prefer OpenAI > Claude > Ollama > Together
        is_complex = len(message) > 300 or any(k in msg for k in _CODE_KEYWORDS)
        if is_complex:
            if ok_openai():    return ('openai',   'gpt-4o')
            if ok_claude():    return ('claude',   'claude-3-5-sonnet-20241022')
            if self._ollama_available: return ('ollama', _OLLAMA_DEFAULT_MODEL)
            if ok_together():  return ('together', 'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo')

        # Default cascade: OpenAI → Claude → Together → Groq → xAI → Ollama
        if ok_openai():    return ('openai',   'gpt-4o')
        if ok_claude():    return ('claude',   'claude-3-5-sonnet-20241022')
        if ok_together():  return ('together', 'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo')
        if ok_groq():      return ('groq',     'llama-3.3-70b-versatile')
        if ok_xai():       return ('xai',      'grok-2-latest')
        if self._ollama_available: return ('ollama', _OLLAMA_DEFAULT_MODEL)
        return (None, None)

    async def _auto_route_with_ollama_model(self, message: str, model_str: str) -> tuple:
        """
        Versão async do resolve que consulta Ollama para descobrir o melhor
        modelo disponível quando a rota vai para 'ollama'.
        """
        self._ollama_available = _ollama_is_available_sync()
        client_type, model_name = self._resolve_model(message, model_str)
        if client_type == 'ollama':
            model_name = await _ollama_best_model_async(model_name or _OLLAMA_DEFAULT_MODEL)
        return client_type, model_name

    def _get_client(self, client_type: str):
        return {
            'openai':   self.openai_client,
            'claude':   self.claude_client,
            'groq':     self.groq_client,
            'xai':      self.xai_client,
            'together': self.together_client,
            'ollama':   self.ollama_client,    # Ollama — sempre presente
        }.get(client_type)

    # ── Compression helpers ───────────────────────────────────────────────────

    @staticmethod
    def _estimate_chars(messages: List[Dict[str, Any]]) -> int:
        """Quick char-count estimate for history size."""
        total = 0
        for m in messages:
            c = m.get('content', '')
            if isinstance(c, str):
                total += len(c)
            elif isinstance(c, list):
                for block in c:
                    if isinstance(block, dict):
                        total += len(str(block.get('text', '')))
        return total

    def _pick_fast_client(self):
        """Pick the fastest/cheapest available client for compression tasks."""
        if self.config.get("zero_cloud_mode") and self._ollama_available:
            return self.ollama_client, self.config.get("default_model", _OLLAMA_DEFAULT_MODEL)
        # Preference: Groq (fastest) → Together (large/free) → OpenAI mini → any
        if self.groq_client:
            return self.groq_client, 'llama-3.1-8b-instant'
        if self.together_client:
            return self.together_client, 'meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo'
        if self.openai_client:
            return self.openai_client, 'gpt-4o-mini'
        if self.claude_client:
            return None, None  # Claude doesn't use OpenAI client
        return None, None

    def _openai_request_overrides(
        self,
        client,
        reasoning_effort: Optional[str] = None,
    ) -> Dict[str, Any]:
        if client is self.ollama_client:
            effort = reasoning_effort or (
                "none" if self.config.get("reasoning_mode") == "FAST" else "low"
            )
            if effort in {"none", "low", "medium"}:
                return {"reasoning_effort": effort}
        return {}

    async def _run_reflection(
        self,
        original_message: str,
        agent_response: str,
        workspace_path: str = '',
    ) -> Optional[str]:
        """
        Self-Reflection Loop — estilo ReAct + Reflexion.

        Usa um modelo rápido (Groq) para critericar a resposta do agente e
        identificar falhas como: código incompleto, raciocínio incorreto,
        etapas faltando, afirmações falsas.

        Retorna:
          - None se a resposta está OK (nenhuma correção necessária)
          - str com a resposta corrigida se foram encontrados problemas
        """
        fast_client, fast_model = self._pick_fast_client()
        if not fast_client:
            return None  # sem cliente rápido disponível

        critique_prompt = f"""Você é um revisor técnico sênior de sistemas de IA.

## Tarefa original do usuário:
{original_message[:1500]}

## Resposta do agente Luna:
{agent_response[:3000]}

## Sua missão:
Analise criticamente a resposta. Identifique APENAS problemas reais:
1. Código incompleto, com bugs óbvios ou que não compilaria
2. Raciocínio de segurança incorreto (falsos positivos/negativos graves)
3. Passos importantes explicitamente faltando que o usuário vai precisar
4. Afirmações técnicas claramente erradas

Se a resposta está boa o suficiente (mesmo não sendo perfeita), responda APENAS:
APROVADO

Se há problemas críticos, responda APENAS no formato:
REVISAR: <lista concisa dos problemas em até 3 linhas>

NÃO reescreva a resposta completa. NÃO adicione elogios. Seja ultra-objetivo."""

        try:
            resp = await fast_client.chat.completions.create(
                model=fast_model,
                messages=[{"role": "user", "content": critique_prompt}],
                max_tokens=300,
                temperature=0.1,
                stream=False,
                **self._openai_request_overrides(fast_client),
            )
            critique = resp.choices[0].message.content.strip() if resp.choices else ""

            if critique.upper().startswith("APROVADO"):
                return None  # resposta OK

            if "REVISAR:" in critique.upper():
                # Extrai os problemas e gera uma resposta corrigida
                problems = critique.replace("REVISAR:", "").replace("REVISAR: ", "").strip()

                fix_prompt = f"""## Tarefa do usuário:
{original_message[:1500]}

## Resposta anterior (com problemas identificados):
{agent_response[:2500]}

## Problemas encontrados pelo revisor:
{problems}

## Sua missão:
Forneça APENAS as correções necessárias para os problemas acima.
NÃO repita o que estava correto. Seja direto e técnico.
Se houver código para corrigir, forneça apenas o trecho corrigido."""

                fix_resp = await fast_client.chat.completions.create(
                    model=fast_model,
                    messages=[{"role": "user", "content": fix_prompt}],
                    max_tokens=512,
                    temperature=0.3,
                    stream=False,
                    **self._openai_request_overrides(fast_client),
                )
                fix = fix_resp.choices[0].message.content.strip() if fix_resp.choices else ""
                if fix:
                    return f"\n\n---\n🔍 **Revisão automática — correções identificadas:**\n\n{fix}"

        except Exception as e:
            logger.debug(f"[Reflection] erro (não crítico): {e}")

        return None

    async def _compress_to_summary(
        self,
        messages_to_compress: List[Dict[str, Any]],
    ) -> str:
        """
        Compress a list of messages into a dense technical summary string.
        Falls back to a simple join if no fast client is available.
        """
        # Build a readable transcript
        parts = []
        for m in messages_to_compress:
            role = m.get('role', '?').upper()
            content = m.get('content', '')
            if isinstance(content, list):
                content = ' '.join(
                    block.get('text', '') for block in content
                    if isinstance(block, dict) and block.get('type') == 'text'
                )
            content_str = str(content)[:600]  # cap per message
            parts.append(f"{role}: {content_str}")

        transcript = '\n'.join(parts)

        client, model = self._pick_fast_client()
        if not client:
            # Fallback: join last few exchanges verbatim
            return f"[HISTÓRICO ANTERIOR RESUMIDO]\n{transcript[:1_200]}"

        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Você é um assistente especializado em compressão de contexto técnico. "
                            "Crie um resumo denso e preciso da conversa a seguir. "
                            "PRESERVE OBRIGATORIAMENTE: decisões técnicas, código importante, "
                            "bugs encontrados, arquivos modificados, estado do projeto, "
                            "preferências e instruções do usuário, contexto de segurança/audit. "
                            "DESCARTE: saudações, confirmações simples, repetições. "
                            "Output: markdown estruturado, máximo 800 palavras, sem cabeçalho extra."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Comprima este histórico de conversa:\n\n{transcript}",
                    },
                ],
                max_tokens=512,
                **self._openai_request_overrides(client),
            )
            return resp.choices[0].message.content or transcript[:1_200]
        except Exception as e:
            logger.warning(f"Compression LLM call failed ({e}), using truncated transcript")
            return f"[HISTÓRICO ANTERIOR — COMPRESSÃO FALHOU]\n{transcript[:1_200]}"

    # ── History management ────────────────────────────────────────────────────

    def _get_history(self, session_id: str, max_turns: int = 4) -> List[Dict[str, Any]]:
        hist = self.histories.get(session_id, [])
        return hist[-(max_turns * 2):]

    @staticmethod
    def _truncate_for_history(content: Any, max_chars: int = 800) -> Any:
        """Truncate large tool result strings when saving to history to avoid bloat."""
        if isinstance(content, str) and len(content) > max_chars:
            return content[:max_chars] + f'… [+{len(content) - max_chars} chars truncado]'
        return content

    def _save_history_from_msgs(self, session_id: str, msgs: List[Dict[str, Any]]) -> None:
        """
        Persist the full conversation (tool calls + results) from a completed
        streaming loop. Truncates tool result content to avoid history bloat.
        Skips the system prompt (msgs[0]).
        """
        cleaned: List[Dict[str, Any]] = []
        for m in msgs[1:]:  # skip system
            role = m.get('role', '')
            if role == 'tool':
                m_copy = dict(m)
                content = m_copy.get('content', '')
                if isinstance(content, str):
                    content = redact_sensitive_text(content)
                m_copy['content'] = self._truncate_for_history(content)
                cleaned.append(m_copy)
            elif role == 'assistant':
                m_copy = dict(m)
                if isinstance(m_copy.get('content'), str):
                    m_copy['content'] = redact_sensitive_text(m_copy['content'])
                # Also truncate tool_call arguments in assistant messages if huge
                if 'tool_calls' in m_copy:
                    trunc_tcs = []
                    for tc in m_copy['tool_calls']:
                        tc2 = dict(tc)
                        fn = dict(tc2.get('function', {}))
                        args = fn.get('arguments', '')
                        if isinstance(args, str) and len(args) > 400:
                            fn['arguments'] = args[:400] + '…'
                        tc2['function'] = fn
                        trunc_tcs.append(tc2)
                    m_copy['tool_calls'] = trunc_tcs
                cleaned.append(m_copy)
            else:
                m_copy = dict(m)
                if isinstance(m_copy.get('content'), str):
                    m_copy['content'] = redact_sensitive_text(m_copy['content'])
                cleaned.append(m_copy)

        if session_id not in self.histories:
            self.histories[session_id] = []
        self.histories[session_id] = cleaned[-40:]

    def _append_history(self, session_id: str, user: str, assistant: str) -> None:
        """Fallback: save simple text turn (used when history_out not populated)."""
        if session_id not in self.histories:
            self.histories[session_id] = []
        self.histories[session_id].append({"role": "user", "content": redact_sensitive_text(user)})
        self.histories[session_id].append({"role": "assistant", "content": redact_sensitive_text(assistant)})
        self.histories[session_id] = self.histories[session_id][-40:]

    # ── SSE event helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _tool_start_event(call_num: int, name: str, args: Dict) -> str:
        """Emit a tool_start SSE event."""
        # Summarize args for display
        if name == 'web_search':
            summary = f'🔍 {args.get("query", "")}'
        elif name == 'fetch_url':
            summary = f'🌐 {args.get("url", "")}'
        elif name in ('read_file', 'write_file', 'delete_file'):
            summary = f'📄 {args.get("path", "")}'
        elif name == 'list_directory':
            summary = f'📁 {args.get("path", ".")}'
        elif name == 'create_directory':
            summary = f'📂 {args.get("path", "")}'
        else:
            summary = json.dumps(args, ensure_ascii=False)[:80]

        return json.dumps({
            "type": "tool_start",
            "call_num": call_num,
            "name": name,
            "args_summary": summary,
        }, ensure_ascii=False)

    @staticmethod
    def _tool_done_event(call_num: int, name: str, result: str, ok: bool) -> str:
        try:
            parsed = json.loads(result)
            if 'error' in parsed:
                summary = f'❌ {parsed["error"]}'
                ok = False
            elif name == 'web_search':
                n = len(parsed.get('results', []))
                summary = f'✅ {n} resultado(s) encontrado(s)'
            elif name == 'write_file':
                summary = f'✅ Arquivo salvo ({parsed.get("bytes_written", "?")} bytes)'
            elif name == 'fetch_url':
                summary = f'✅ {len(parsed.get("content", ""))} chars lidos'
            elif name == 'list_directory':
                n = len(parsed.get('entries', []))
                summary = f'✅ {n} item(s) listado(s)'
            else:
                summary = '✅ Concluído'
        except Exception:
            summary = result[:80]

        return json.dumps({
            "type": "tool_done",
            "call_num": call_num,
            "name": name,
            "result_summary": summary,
            "ok": ok,
        }, ensure_ascii=False)

    # ── Streaming core — OpenAI-compatible with tool loop ─────────────────────

    async def _stream_openai_with_tools(
        self,
        client,
        model_name: str,
        messages: List[Dict[str, Any]],
        system: str,
        workspace: str,
        call_counter: list,   # mutable counter passed by ref
        history_out: list,    # populated at end with full msgs (sans system prompt)
        reasoning_effort: Optional[str] = None,
        turn_telemetry: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        OpenAI-compatible streaming with tool-calling loop.
        Yields JSON SSE event strings (without the 'data: ' prefix).
        At completion, history_out is populated with the full conversation
        (tool calls + results included) so the caller can persist it.
        """
        supervised_local = (
            client is self.ollama_client
            and not self._tool_execution_allowed()
        )
        if supervised_local:
            # A real system role keeps runtime facts above Modelfile few-shot examples.
            # It also avoids making internal guards look like part of the user's prose.
            msgs = [{"role": "system", "content": system}, *messages]
        else:
            msgs = [{"role": "system", "content": system}, *messages]
        iteration = 0

        while iteration < self.MAX_TOOL_ITERATIONS:
            iteration += 1
            text_buf = ''
            tool_calls_buf: Dict[int, Dict] = {}  # index → {id, name, args_str}

            # ── Stream one LLM turn ─────────────────────────────────────────
            max_tokens = self.config["max_tokens"]
            route_name = (turn_telemetry or {}).get("route")
            if reasoning_effort == "low":
                max_tokens = 256
            elif reasoning_effort == "medium":
                max_tokens = 384
            elif route_name == "ANALYZE":
                max_tokens = max(max_tokens, 1_024)
            elif route_name == "DEEP":
                max_tokens = max(max_tokens, 1_536)
            request_kwargs: Dict[str, Any] = {
                "model": model_name,
                "messages": msgs,
                # Ollama counts hidden reasoning and visible answer in this budget.
                # Keep FAST lean while reserving enough room for a final answer.
                "max_tokens": max_tokens,
                "stream": True,
                **self._openai_request_overrides(client, reasoning_effort),
            }
            if self.config.get("temperature") is not None:
                request_kwargs["temperature"] = self.config["temperature"]
            if self._tool_execution_allowed():
                request_kwargs["tools"] = TOOL_DEFINITIONS
                request_kwargs["tool_choice"] = "auto"

            request_started = time.perf_counter()
            first_token_ms: Optional[float] = None
            chunk_count = 0
            finish_reason: Optional[str] = None
            request_failed = False
            is_ollama = client is self.ollama_client
            if turn_telemetry is not None:
                turn_telemetry["llm_called"] = True
                turn_telemetry["request_count"] = int(turn_telemetry.get("request_count", 0)) + 1
                turn_telemetry.setdefault("attempt_efforts", []).append(reasoning_effort or "none")
            if is_ollama:
                logger.info(
                    "ollama.request.start %s",
                    json.dumps(
                        {
                            "session_id": (turn_telemetry or {}).get("session_id", "default"),
                            "model": model_name,
                            "reasoning_effort": reasoning_effort or "none",
                            "max_tokens": max_tokens,
                            "request_index": (turn_telemetry or {}).get("request_count", 1),
                        },
                        ensure_ascii=False,
                    ),
                )

            try:
                stream = await client.chat.completions.create(**request_kwargs)

                async for chunk in stream:
                    chunk_count += 1
                    choice = chunk.choices[0] if chunk.choices else None
                    if choice and choice.finish_reason:
                        finish_reason = str(choice.finish_reason)
                    delta = choice.delta if choice else None
                    if delta is None:
                        continue

                    # Only final answer content is forwarded. Provider-specific reasoning
                    # fields are intentionally ignored and never persisted.
                    if delta.content:
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - request_started) * 1000
                        text_buf += delta.content
                        yield json.dumps({"type": "text_chunk", "text": delta.content}, ensure_ascii=False)

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_buf:
                                tool_calls_buf[idx] = {"id": tc.id or "", "name": "", "args_str": ""}
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_buf[idx]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_buf[idx]["args_str"] += tc.function.arguments
            except Exception:
                request_failed = True
                raise
            finally:
                elapsed_ms = (time.perf_counter() - request_started) * 1000
                if turn_telemetry is not None:
                    turn_telemetry["chunks"] = int(turn_telemetry.get("chunks", 0)) + chunk_count
                    turn_telemetry["elapsed_ms"] = round(elapsed_ms, 1)
                    turn_telemetry["first_token_ms"] = (
                        round(first_token_ms, 1) if first_token_ms is not None else None
                    )
                    turn_telemetry["finish_reason"] = finish_reason or (
                        "error" if request_failed else "unknown"
                    )
                    turn_telemetry.setdefault("attempt_results", []).append({
                        "effort": reasoning_effort or "none",
                        "elapsed_ms": round(elapsed_ms, 1),
                        "first_token_ms": (
                            round(first_token_ms, 1) if first_token_ms is not None else None
                        ),
                        "chunks": chunk_count,
                        "finish_reason": finish_reason or (
                            "error" if request_failed else "unknown"
                        ),
                    })
                if is_ollama:
                    logger.info(
                        "ollama.request.done %s",
                        json.dumps(
                            {
                                "session_id": (turn_telemetry or {}).get("session_id", "default"),
                                "model": model_name,
                                "elapsed_ms": round(elapsed_ms, 1),
                                "first_token_ms": round(first_token_ms, 1) if first_token_ms is not None else None,
                                "chunks": chunk_count,
                                "finish_reason": finish_reason or ("error" if request_failed else "unknown"),
                            },
                            ensure_ascii=False,
                        ),
                    )

            # ── If no tool calls, we're done ────────────────────────────────
            if not tool_calls_buf:
                # Append final assistant text message so it's in history
                msgs.append({"role": "assistant", "content": text_buf or ''})
                break

            # ── Execute tool calls ──────────────────────────────────────────
            if not self._tool_execution_allowed():
                logger.error(
                    "Blocked unexpected model tool call in instruction-only build: %s",
                    [item.get("name", "") for item in tool_calls_buf.values()],
                )
                msgs.append({"role": "assistant", "content": text_buf or ""})
                break

            # Add assistant message with tool_calls to history
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": text_buf or None}
            assistant_tool_calls = []

            for idx in sorted(tool_calls_buf.keys()):
                tc = tool_calls_buf[idx]
                call_counter[0] += 1
                call_num = call_counter[0]

                try:
                    args = json.loads(tc["args_str"] or '{}')
                except json.JSONDecodeError:
                    args = {}

                yield LunaEngine._tool_start_event(call_num, tc["name"], args)

                result_str = await execute_tool(tc["name"], args, workspace)
                ok = '"error"' not in result_str

                # Special frontend action (e.g. open_workspace_dialog, project_context_updated)
                try:
                    parsed_result = json.loads(result_str)
                    if isinstance(parsed_result, dict) and '__action__' in parsed_result:
                        yield json.dumps({"type": "frontend_action", **parsed_result}, ensure_ascii=False)
                except Exception:
                    pass

                # Emit file_accessed event so frontend can track active files
                _FILE_OPS = {'read_file': 'read', 'write_file': 'write',
                             'list_directory': 'list', 'create_directory': 'write'}
                if tc["name"] in _FILE_OPS:
                    yield json.dumps({
                        "type": "file_accessed",
                        "path": args.get('path', '.'),
                        "operation": _FILE_OPS[tc["name"]],
                    }, ensure_ascii=False)

                yield LunaEngine._tool_done_event(call_num, tc["name"], result_str, ok)

                assistant_tool_calls.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["args_str"]},
                })
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str,
                })

            assistant_msg["tool_calls"] = assistant_tool_calls
            # Insert assistant msg before the tool results
            msgs.insert(len(msgs) - len(tool_calls_buf), assistant_msg)

        # ── Expose full conversation to caller for history persistence ──────
        if supervised_local:
            final_assistant = msgs[-1] if msgs and msgs[-1].get("role") == "assistant" else None
            persisted = [{"role": "system", "content": ""}, *messages]
            if final_assistant:
                persisted.append(final_assistant)
            history_out[:] = persisted
        else:
            # System prompt at msgs[0] is stripped by the history saver.
            history_out[:] = msgs

    # ── Streaming core — Anthropic with tool loop ─────────────────────────────

    async def _stream_claude_with_tools(
        self,
        model_name: str,
        messages: List[Dict[str, Any]],
        system: str,
        workspace: str,
        call_counter: list,
        history_out: list,   # populated at end with simplified conversation history
    ) -> AsyncIterator[str]:
        """
        Anthropic streaming with tool-calling loop.
        At completion, history_out is populated with a simplified text-based history
        (Claude tool_use blocks are not JSON-serialisable, so we flatten them).
        """
        msgs = list(messages)
        iteration = 0
        # Parallel simplified history in OpenAI-compatible format for persistence
        simple_history: List[Dict[str, Any]] = list(messages)

        while iteration < self.MAX_TOOL_ITERATIONS:
            iteration += 1

            request_kwargs: Dict[str, Any] = {
                "model": model_name,
                "max_tokens": self.config["max_tokens"],
                "system": system,
                "messages": msgs,
            }
            if self._tool_execution_allowed():
                request_kwargs["tools"] = TOOL_DEFINITIONS_CLAUDE

            async with self.claude_client.messages.stream(**request_kwargs) as stream:
                full_response = await stream.get_final_message()

            # Stream text blocks
            text_content = ''
            tool_use_blocks = []

            for block in full_response.content:
                if block.type == 'text':
                    text_content += block.text
                    # Yield in chunks for consistent UX
                    words = block.text.split(' ')
                    buf = ''
                    for w in words:
                        buf += w + ' '
                        if len(buf) >= 40:
                            yield json.dumps({"type": "text_chunk", "text": buf}, ensure_ascii=False)
                            buf = ''
                    if buf:
                        yield json.dumps({"type": "text_chunk", "text": buf}, ensure_ascii=False)

                elif block.type == 'tool_use':
                    tool_use_blocks.append(block)

            if not tool_use_blocks:
                # Done — save final assistant text to simple history
                simple_history.append({"role": "assistant", "content": text_content})
                break

            if not self._tool_execution_allowed():
                logger.error(
                    "Blocked unexpected Claude tool call in instruction-only build: %s",
                    [getattr(block, "name", "") for block in tool_use_blocks],
                )
                simple_history.append({"role": "assistant", "content": text_content})
                break

            # Add assistant message (Anthropic native format for current loop)
            msgs.append({"role": "assistant", "content": full_response.content})

            # Build tool summary for simplified history
            tool_summary_parts = [text_content] if text_content else []

            # Execute tools
            tool_results = []
            for block in tool_use_blocks:
                call_counter[0] += 1
                call_num = call_counter[0]
                args = dict(block.input) if block.input else {}

                yield LunaEngine._tool_start_event(call_num, block.name, args)
                result_str = await execute_tool(block.name, args, workspace)
                ok = '"error"' not in result_str

                # Special frontend action (e.g. open_workspace_dialog, project_context_updated)
                try:
                    parsed_result = json.loads(result_str)
                    if isinstance(parsed_result, dict) and '__action__' in parsed_result:
                        yield json.dumps({"type": "frontend_action", **parsed_result}, ensure_ascii=False)
                except Exception:
                    pass

                # Emit file_accessed event
                _FILE_OPS = {'read_file': 'read', 'write_file': 'write',
                             'list_directory': 'list', 'create_directory': 'write'}
                if block.name in _FILE_OPS:
                    yield json.dumps({
                        "type": "file_accessed",
                        "path": args.get('path', '.'),
                        "operation": _FILE_OPS[block.name],
                    }, ensure_ascii=False)

                yield LunaEngine._tool_done_event(call_num, block.name, result_str, ok)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

                # Collect for simplified history (truncated)
                result_snippet = self._truncate_for_history(result_str, 400)
                tool_summary_parts.append(f'[tool:{block.name}] → {result_snippet}')

            msgs.append({"role": "user", "content": tool_results})

            # Add assistant+tools turn to simplified history
            simple_history.append({
                "role": "assistant",
                "content": '\n'.join(tool_summary_parts),
            })

        # ── Expose simplified history to caller ──────────────────────────────
        history_out[:] = simple_history

    # ── Public streaming entry point ──────────────────────────────────────────

    @staticmethod
    def _build_vision_content(
        text: str,
        images: Optional[List[Dict[str, str]]],
        client_type: str,
    ) -> Any:
        """
        Constrói o campo `content` da mensagem com suporte a imagens.

        images = [{"data": "<base64>", "mime": "image/png"}, ...]

        - OpenAI/Groq/Ollama/xAI/Together: content = list de {type, text/image_url}
        - Claude/Anthropic: content = list de {type, text/image/source}
        """
        if not images:
            return text   # mensagem de texto puro — sem mudanças

        if client_type == 'claude':
            parts: List[Dict] = []
            for img in images:
                parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("mime", "image/png"),
                        "data": img["data"],
                    }
                })
            parts.append({"type": "text", "text": text})
            return parts
        else:
            # OpenAI-compatible format (também funciona em Ollama com llava/bakllava)
            parts = []
            for img in images:
                parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.get('mime','image/png')};base64,{img['data']}",
                        "detail": "high",
                    }
                })
            parts.append({"type": "text", "text": text})
            return parts

    async def stream_agent(
        self,
        message: str,
        session_id: str = "default",
        model_str: str = _OLLAMA_DEFAULT_MODEL,
        workspace_path: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
        user_context: Optional[str] = None,
        project_context: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Primary streaming method. Yields JSON strings for SSE delivery.
        Handles tool-calling loop automatically.

        images: lista de {"data": "<base64 string>", "mime": "image/png|jpeg|webp|gif"}
        """
        turn_started = time.perf_counter()
        scenario = self.scenario_contexts.setdefault(session_id, ScenarioContext())
        evidence_delta = scenario.update(message, project_context=project_context)
        history = self._get_history(session_id)
        route = classify_complexity(
            message,
            evidence_delta_count=evidence_delta.count,
            scenario=scenario.to_dict(),
            history=history,
            mentor_enabled=bool(self.config.get("mentor_mode")),
        )
        turn_telemetry: Dict[str, Any] = {
            "session_id": session_id,
            "route": route.route,
            "reasoning_effort": route.reasoning_effort,
            "route_reasons": list(route.reasons),
            "llm_required": route.llm_required,
            "llm_called": False,
            "evidence_delta_count": evidence_delta.count,
            "selected_modules": list(route.selected_modules),
            "loop_guard": "pending",
            "response_source": "system_error",
            "request_count": 0,
            "chunks": 0,
        }

        # Resolve model — usa versão async para descobrir modelo Ollama disponível
        client_type, model_name = await self._auto_route_with_ollama_model(message, model_str)
        client = self._get_client(client_type) if client_type else None
        turn_telemetry["provider"] = client_type
        turn_telemetry["model"] = model_name
        effective_reasoning_effort = route.reasoning_effort
        if (
            client_type == "ollama"
            and route.reasoning_effort in {"low", "medium"}
            and not self.config.get("native_reasoning_effort")
        ):
            effective_reasoning_effort = "none"
            turn_telemetry["effort_fallback_reason"] = (
                "qwen4b_hidden_reasoning_exhausts_visible_output_budget"
            )
        turn_telemetry["effective_reasoning_effort"] = effective_reasoning_effort

        if client_type == 'ollama' and not self._ollama_available:
            turn_telemetry["loop_guard"] = "not_run"
            self.turn_metadata[session_id] = dict(turn_telemetry)
            logger.warning(
                "chat.response.no_llm reason=ollama_unavailable session_id=%s",
                session_id,
            )
            yield json.dumps({
                "type": "error",
                "message": "Ollama não está acessível em localhost:11434.",
                "response_source": "system_error",
                "llm_called": False,
            }, ensure_ascii=False)
            return

        if not client or not model_name:
            # Último recurso: tenta Ollama mesmo sem detecção prévia
            if _ollama_is_available_sync():
                self._ollama_available = True
                client_type = 'ollama'
                model_name = await _ollama_best_model_async()
                client = self.ollama_client
                yield json.dumps({"type": "text_chunk", "text":
                    f"🦙 *Modo local ativado automaticamente — usando Ollama ({model_name})*\n\n"
                }, ensure_ascii=False)
            else:
                turn_telemetry["loop_guard"] = "not_run"
                self.turn_metadata[session_id] = dict(turn_telemetry)
                logger.warning(
                    "chat.response.no_llm reason=no_local_model session_id=%s",
                    session_id,
                )
                yield json.dumps({
                    "type": "error",
                    "message": (
                        "Nenhum modelo local está disponível. Confirme o Ollama e o "
                        "modelo luna-cyber-fast; nenhum fallback cloud foi usado."
                    ),
                    "response_source": "system_error",
                    "llm_called": False,
                }, ensure_ascii=False)
                return

        # Emite evento informando qual provedor/modelo será usado
        zero_cloud = self.config.get("zero_cloud_mode", False)
        if zero_cloud and client_type == 'ollama':
            yield json.dumps({"type": "provider_info", "provider": "ollama",
                "model": model_name, "mode": "zero_cloud", "route": route.route,
                "reasoning_effort": route.reasoning_effort,
                "effective_reasoning_effort": effective_reasoning_effort,
                "llm_required": True}, ensure_ascii=False)
        elif client_type == 'ollama':
            yield json.dumps({"type": "provider_info", "provider": "ollama",
                "model": model_name, "mode": "local_fallback", "route": route.route,
                "reasoning_effort": route.reasoning_effort,
                "effective_reasoning_effort": effective_reasoning_effort,
                "llm_required": True}, ensure_ascii=False)

        # ── Auto-compress if history is too long ──────────────────────────────
        needs_compress = (
            len(history) >= self.COMPRESS_THRESHOLD or
            self._estimate_chars(history) >= self.COMPRESS_MAX_CHARS
        )
        ctx_summary: Optional[str] = self.compression_summaries.get(session_id)

        if needs_compress:
            # Compress older messages, keep the most recent turns verbatim
            to_compress = history[:-self.COMPRESS_KEEP_RECENT]
            keep_recent = history[-self.COMPRESS_KEEP_RECENT:]

            if to_compress:
                yield json.dumps({"type": "compressing", "progress": 0,
                    "message": "Compactando conversa para continuar..."}, ensure_ascii=False)

                # Prepend any previous summary
                if ctx_summary:
                    to_compress = [{"role": "system", "content": f"[RESUMO ANTERIOR]\n{ctx_summary}"}] + to_compress

                yield json.dumps({"type": "compressing", "progress": 40,
                    "message": "Processando memória..."}, ensure_ascii=False)

                new_summary = await self._compress_to_summary(to_compress)

                yield json.dumps({"type": "compressing", "progress": 80,
                    "message": "Finalizando..."}, ensure_ascii=False)

                # Store new accumulated summary and trim history
                self.compression_summaries[session_id] = new_summary
                self.histories[session_id] = keep_recent
                history = keep_recent
                ctx_summary = new_summary

                yield json.dumps({"type": "compressing", "progress": 100,
                    "message": "Pronto — contexto preservado"}, ensure_ascii=False)

        runtime_modules: Dict[str, str] = {}
        for module_id in route.selected_modules:
            content = self.active_modules.get(module_id)
            if content:
                runtime_modules[module_id] = self.module_loader.relevant_excerpt(
                    content,
                    f"{message}\n{scenario.to_prompt_block(600)}",
                    max_chars=650,
                )
        turn_telemetry["selected_modules"] = sorted(runtime_modules)

        if route.route == "FAST":
            route_guidance = (
                "Responda diretamente e com brevidade. Em saudação, apenas cumprimente e "
                "pergunte como ajudar; não invente alvo, evidência ou comando."
            )
        elif route.route == "ANALYZE":
            route_guidance = (
                "Correlacione a evidência atual, separe fato de inferência e proponha no "
                "máximo a próxima ação de maior ganho de informação."
            )
        else:
            route_guidance = (
                "Faça decomposição cuidadosa dos artefatos e fronteiras de confiança antes "
                "de propor no máximo a próxima ação de maior ganho de informação."
            )
        route_instruction = (
            f"AUTO REASONING: route={route.route}; effort={route.reasoning_effort}. "
            f"{route_guidance} Nunca repita ação já resolvida sem justificar um reteste."
        )
        if not scenario.target:
            route_instruction += (
                " Nenhum target/host factual foi observado: descreva eventual teste somente "
                "por método e path; não escreva curl, hostname, porta ou URL placeholder."
            )

        construction_context = construction_guidance(
            f"{message}\n{scenario.to_prompt_block(650)}"
        )
        if construction_context:
            route_instruction += " " + construction_context

        # Core reasoning guidance comes before tool/capability detail so it
        # survives the compact route-instruction budget used by the 4B model.
        decision_context = decision_guidance(
            f"{message}\n{scenario.to_prompt_block(700)}"
        )
        if decision_context:
            route_instruction += " " + decision_context

        tool_guidance = guidance_for_context(message, scenario=scenario, history=history)
        if tool_guidance:
            route_instruction += " " + tool_guidance

        capability_context = technical_guidance(message)
        if capability_context:
            route_instruction += " " + capability_context

        if any(
            marker in message.casefold()
            for marker in (
                "sudo", "systemctl", "iptables", "nft", "ufw", "route", "disco",
                "disk", "partição", "partition", "boot", "grub", "bcd", "rm ",
                "chmod", "chown", "instale", "install", "configure", "configurar",
            )
        ):
            route_instruction += " " + host_safety_guidance(message)

        malware_context = malware_guidance(
            f"{message}\n{scenario.to_prompt_block(600)}"
        )
        if malware_context:
            route_instruction += " " + malware_context
            route_instruction += " MALWARE TOOLING: " + malware_tooling_summary()
            response_context = threat_response_guidance(
                f"{message}\n{scenario.to_prompt_block(600)}"
            )
            if response_context:
                route_instruction += " " + response_context

        system = _build_system_prompt(
            workspace_path,
            context_summary=ctx_summary,
            user_context=user_context,
            scenario_context=scenario.to_prompt_block(),
            evidence_delta=evidence_delta.to_prompt_block(),
            route_instruction=route_instruction,
            project_context=project_context,
            active_modules=runtime_modules,
            supervised_mode=not self._tool_execution_allowed(),
        )
        # Monta content — inclui imagens se fornecidas
        user_content = self._build_vision_content(message, images, client_type)
        messages = [*history, {"role": "user", "content": user_content}]
        call_ctr = [0]   # mutable so sub-generators can increment
        full_text = ''
        history_out: list = []  # populated by streaming loop with full tool-call history
        validation = None
        replan_used = False

        async def collect_generation(generator: AsyncIterator[str]) -> tuple[List[str], str]:
            buffered_events: List[str] = []
            buffered_text = ""
            async for event_json in generator:
                buffered_events.append(event_json)
                try:
                    event = json.loads(event_json)
                    if event.get("type") == "text_chunk":
                        buffered_text += str(event.get("text", ""))
                except (TypeError, json.JSONDecodeError):
                    continue
            return buffered_events, buffered_text

        try:
            if client_type == 'claude':
                gen = self._stream_claude_with_tools(
                    model_name, messages, system, workspace_path or '', call_ctr, history_out)
            else:
                gen = self._stream_openai_with_tools(
                    client,
                    model_name,
                    messages,
                    system,
                    workspace_path or '',
                    call_ctr,
                    history_out,
                    effective_reasoning_effort,
                    turn_telemetry,
                )

            buffered_events, full_text = await collect_generation(gen)
            validation = validate_model_response(
                message=message,
                response=full_text,
                scenario=scenario,
                evidence_delta_count=evidence_delta.count,
            )

            if not validation.valid:
                replan_used = True
                logger.info(
                    "chat.response.replan %s",
                    json.dumps(
                        {
                            "session_id": session_id,
                            "route": route.route,
                            "reasons": list(validation.reasons),
                            "loop_guard": validation.loop_guard,
                        },
                        ensure_ascii=False,
                    ),
                )
                replan_instruction = build_replan_instruction(
                    validation,
                    scenario.to_prompt_block(500),
                    message,
                )
                normalized_message = message.casefold()
                if (
                    "apenas um comando" in normalized_message
                    or "somente um comando" in normalized_message
                ):
                    observed_bearer = re.search(
                        r"(?i)Authorization\s*:\s*Bearer\s+([^\s\r\n]+)",
                        message,
                    )
                    if observed_bearer:
                        replan_instruction = (
                            "REQUISITO CRÍTICO: o único comando deve conter literalmente, sem "
                            "placeholder: Authorization: Bearer "
                            f"{observed_bearer.group(1)}\n\n"
                            + replan_instruction
                        )
                replan_effort = (
                    "none" if "empty_model_response" in validation.reasons
                    else effective_reasoning_effort
                )
                turn_telemetry["replan_reasoning_effort"] = replan_effort
                replan_messages = [
                    *messages,
                    {"role": "user", "content": replan_instruction},
                ]
                replan_history: list = []
                if client_type == 'claude':
                    replan_gen = self._stream_claude_with_tools(
                        model_name,
                        replan_messages,
                        system,
                        workspace_path or '',
                        call_ctr,
                        replan_history,
                    )
                else:
                    replan_gen = self._stream_openai_with_tools(
                        client,
                        model_name,
                        replan_messages,
                        system,
                        workspace_path or '',
                        call_ctr,
                        replan_history,
                        replan_effort,
                        turn_telemetry,
                    )
                buffered_events, full_text = await collect_generation(replan_gen)
                validation = validate_model_response(
                    message=message,
                    response=full_text,
                    scenario=scenario,
                    evidence_delta_count=evidence_delta.count,
                )
                if replan_history:
                    history_out[:] = replan_history

            if validation and not validation.valid:
                turn_telemetry.update({
                    "response_source": "system_error",
                    "loop_guard": "replan_failed_validation",
                    "validator_passed": False,
                    "replan_used": replan_used,
                    "validation_reasons": list(validation.reasons),
                    "total_elapsed_ms": round((time.perf_counter() - turn_started) * 1000, 1),
                })
                self.turn_metadata[session_id] = dict(turn_telemetry)
                logger.info(
                    "chat.route %s",
                    json.dumps(turn_telemetry, ensure_ascii=False),
                )
                logger.error(
                    "chat.response.rejected %s",
                    json.dumps(
                        {
                            "session_id": session_id,
                            "route": route.route,
                            "reasons": list(validation.reasons),
                            "llm_called": turn_telemetry["llm_called"],
                            "request_count": turn_telemetry["request_count"],
                        },
                        ensure_ascii=False,
                    ),
                )
                yield json.dumps({
                    "type": "error",
                    "message": (
                        "O modelo local não produziu uma resposta factual validável após "
                        "uma tentativa de replanejamento. Nenhuma resposta insegura foi exibida."
                    ),
                    "response_source": "system_error",
                    "llm_called": True,
                }, ensure_ascii=False)
                return

            for event_json in buffered_events:
                yield event_json

        except Exception as e:
            logger.error(f"Stream error [{client_type}/{model_name}]: {e}")

            if client_type == 'ollama':
                self._ollama_available = _ollama_is_available_sync()
                if not self._ollama_available:
                    friendly = "Ollama não está acessível em localhost:11434."
                else:
                    friendly = (
                        f"Falha ao usar o modelo local `{model_name}`. "
                        "Confirme o nome com `ollama list`; nenhum fallback cloud foi usado."
                    )
                turn_telemetry.update({
                    "response_source": "system_error",
                    "loop_guard": "generation_error",
                    "total_elapsed_ms": round((time.perf_counter() - turn_started) * 1000, 1),
                })
                self.turn_metadata[session_id] = dict(turn_telemetry)
                logger.warning(
                    "chat.response.no_llm %s",
                    json.dumps(
                        {
                            "session_id": session_id,
                            "reason": "ollama_generation_error",
                            "llm_called": turn_telemetry["llm_called"],
                        },
                        ensure_ascii=False,
                    ),
                )
                yield json.dumps({
                    "type": "error",
                    "message": friendly,
                    "response_source": "system_error",
                    "llm_called": turn_telemetry["llm_called"],
                }, ensure_ascii=False)
                return

            err_str = str(e)
            is_auth_error = any(x in err_str.lower() for x in (
                '401', 'authentication', 'invalid x-api-key', 'invalid_api_key',
                'incorrect api key', 'api key', 'unauthorized',
            ))
            is_cloud = client_type != 'ollama'

            # Marca provedor com key inválida para não usar nas próximas chamadas
            if is_auth_error and client_type:
                self._bad_key_providers.add(client_type)
                logger.warning(f"🔑 {client_type} marcado como key inválida — será ignorado nas próximas chamadas")

            # ── Cascata de fallback entre provedores cloud (ex: Claude 401 → OpenAI → Groq) ──
            if is_cloud and is_auth_error:
                # Ordem de fallback: openai → groq → together → xai → Ollama
                _cloud_fallbacks = [
                    ('openai',   'gpt-4o',                    self.openai_client),
                    ('groq',     'llama-3.3-70b-versatile',   self.groq_client),
                    ('together', 'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo', self.together_client),
                    ('xai',      'grok-2-latest',             self.xai_client),
                ]
                for fb_type, fb_model, fb_client in _cloud_fallbacks:
                    if fb_type == client_type or not fb_client:
                        continue  # pula o provedor que falhou e os que não têm key
                    logger.warning(f"🔑 Auth error [{client_type}] — tentando {fb_type}/{fb_model}")
                    yield json.dumps({"type": "text_chunk", "text":
                        f"\n\n⚠️ *{client_type} — chave inválida. Alternando para {fb_type}...*\n\n"
                    }, ensure_ascii=False)
                    fb_history_out: list = []
                    try:
                        fb_gen = self._stream_openai_with_tools(
                            fb_client, fb_model,
                            messages, system, workspace_path or '', call_ctr, fb_history_out
                        )
                        async for event_json in fb_gen:
                            try:
                                ev = json.loads(event_json)
                                if ev.get("type") == "text_chunk":
                                    full_text += ev.get("text", "")
                            except Exception:
                                pass
                            yield event_json
                        if fb_history_out:
                            history_out[:] = fb_history_out
                        return  # fallback cloud completou
                    except Exception as fb_err:
                        logger.warning(f"Fallback {fb_type} também falhou: {fb_err}")
                        continue  # tenta o próximo

            # ── Fallback para Ollama local ────────────────────────────────────
            if is_cloud and self._ollama_available and not self.config.get("zero_cloud_mode"):
                fallback_model = await _ollama_best_model_async()
                logger.warning(f"☁️  Cloud falhou — tentando Ollama local ({fallback_model})")
                yield json.dumps({"type": "text_chunk", "text":
                    f"\n\n⚠️ *Provedores cloud indisponíveis — alternando para Ollama local ({fallback_model})...*\n\n"
                }, ensure_ascii=False)

                fallback_history_out: list = []
                try:
                    fallback_gen = self._stream_openai_with_tools(
                        self.ollama_client, fallback_model,
                        messages, system, workspace_path or '', call_ctr, fallback_history_out
                    )
                    async for event_json in fallback_gen:
                        try:
                            ev = json.loads(event_json)
                            if ev.get("type") == "text_chunk":
                                full_text += ev.get("text", "")
                        except Exception:
                            pass
                        yield event_json

                    if fallback_history_out:
                        history_out[:] = fallback_history_out
                    return  # fallback completou — não propaga o erro original

                except Exception as e2:
                    logger.error(f"Ollama fallback também falhou: {e2}")

            # ── Erro final — mensagem amigável sem expor detalhes da API ─────
            if is_auth_error:
                friendly = (
                    f"**Chave de API inválida** para `{client_type}`.\n\n"
                    f"Vá em **Settings → Provedores** e atualize a chave do `{client_type}`. "
                    f"Se não tiver chave, use o modelo **Groq** (gratuito) ou ative o **Modo Zero-Cloud** com Ollama."
                )
            else:
                friendly = f"Erro de conexão com `{client_type}`. Verifique sua internet e tente novamente."

            yield json.dumps({"type": "text_chunk", "text": f"\n\n⚠️ {friendly}"}, ensure_ascii=False)
            return

        # ── Self-Reflection Loop (se habilitado e texto longo o suficiente) ────
        reflection_enabled = self.config.get("reflection_enabled", False)
        if reflection_enabled and full_text and len(full_text) > 200:
            yield json.dumps({"type": "reflecting", "message": "🔍 Revisando resposta..."}, ensure_ascii=False)
            try:
                correction = await self._run_reflection(message, full_text, workspace_path or '')
                if correction:
                    yield json.dumps({"type": "text_chunk", "text": correction}, ensure_ascii=False)
                    full_text += correction
                    # Atualiza o histórico com a versão corrigida
                    if history_out:
                        for entry in reversed(history_out):
                            if entry.get("role") == "assistant":
                                entry["content"] = full_text
                                break
                    yield json.dumps({"type": "reflection_done", "had_corrections": True}, ensure_ascii=False)
                else:
                    yield json.dumps({"type": "reflection_done", "had_corrections": False}, ensure_ascii=False)
            except Exception as reflection_error:
                logger.debug(f"[Reflection] ignorado: {reflection_error}")

        if full_text:
            scenario.record_model_response(full_text)

        turn_telemetry.update({
            "response_source": "model",
            "loop_guard": (
                "replan_passed" if replan_used and validation and validation.valid
                else "replan_failed_validation" if replan_used
                else validation.loop_guard if validation
                else "not_validated"
            ),
            "validator_passed": bool(validation and validation.valid),
            "replan_used": replan_used,
            "validation_reasons": list(validation.reasons) if validation else [],
            "proposed_action_fingerprint": (
                validation.proposed_action_fingerprint if validation else None
            ),
            "total_elapsed_ms": round((time.perf_counter() - turn_started) * 1000, 1),
        })
        self.turn_metadata[session_id] = dict(turn_telemetry)
        logger.info(
            "chat.route %s",
            json.dumps(
                {
                    key: turn_telemetry.get(key)
                    for key in (
                        "session_id", "route", "reasoning_effort", "route_reasons",
                        "evidence_delta_count", "selected_modules", "loop_guard",
                        "response_source", "llm_called", "request_count", "chunks",
                        "first_token_ms", "elapsed_ms", "total_elapsed_ms",
                        "finish_reason", "validator_passed", "replan_used",
                        "attempt_efforts", "replan_reasoning_effort",
                        "attempt_results",
                        "effective_reasoning_effort", "effort_fallback_reason",
                    )
                },
                ensure_ascii=False,
            ),
        )
        yield json.dumps({"type": "response_meta", **turn_telemetry}, ensure_ascii=False)

        # Persist full conversation including tool calls (not just final text)
        if history_out:
            self._save_history_from_msgs(session_id, history_out)
        elif full_text:
            # Fallback: save text-only if history_out wasn't populated
            self._append_history(session_id, message, full_text)

    # ── Legacy / non-streaming ────────────────────────────────────────────────

    async def process_message(self, message: str, conversation_id: str = "default",
                              model: Optional[ModelProvider] = None) -> ChatResponse:
        model_str = model.value if model else _OLLAMA_DEFAULT_MODEL
        full = ""
        async for ev_json in self.stream_agent(message, conversation_id, model_str):
            try:
                ev = json.loads(ev_json)
                if ev.get("type") == "text_chunk":
                    full += ev.get("text", "")
            except Exception:
                pass
        return ChatResponse(
            response=full,
            model=model or ModelProvider.OLLAMA,
            tokens_used=len(full.split()) // 3,
            conversation_id=conversation_id,
        )

    async def stream_response(self, message: str, conversation_id: str = "default", model=None):
        model_str = model.value if model else _OLLAMA_DEFAULT_MODEL
        async for ev_json in self.stream_agent(message, conversation_id, model_str):
            try:
                ev = json.loads(ev_json)
                if ev.get("type") == "text_chunk":
                    yield ev.get("text", "")
            except Exception:
                pass

    async def get_short_term_memory(self, conversation_id: str):
        hist = self.histories.get(conversation_id, [])
        return [{"role": m["role"], "content": str(m.get("content", ""))[:200]} for m in hist]

    async def search_long_term_memory(self, query: str, limit: int = 5):
        results = []
        q = query.lower()
        for sid, hist in self.histories.items():
            for m in hist:
                content = str(m.get("content", ""))
                if q in content.lower():
                    results.append({"session": sid, "content": content[:200]})
        return results[:limit]

    async def clear_memory(self, conversation_id: str) -> None:
        self.histories.pop(conversation_id, None)
        # Also clear compressed summary so old context isn't re-injected after reset
        self.compression_summaries.pop(conversation_id, None)
        self.scenario_contexts.pop(conversation_id, None)

    def get_scenario_context(self, conversation_id: str) -> Dict[str, Any]:
        context = self.scenario_contexts.get(conversation_id)
        return context.to_dict() if context else {}

    def get_local_diagnostics(self) -> Dict[str, Any]:
        self._ollama_available = _ollama_is_available_sync()
        return {
            "ollama": self._ollama_available,
            "ollama_base_url": OLLAMA_BASE_URL,
            "default_model": self.config["default_model"],
            "zero_cloud_mode": bool(self.config["zero_cloud_mode"]),
            "instruction_only_mode": bool(self.config.get("instruction_only_mode", True)),
            "supervised_mode": not self._tool_execution_allowed(),
            "tool_execution_allowed": self._tool_execution_allowed(),
            "config_dir": str(self.module_loader.config_dir),
            "modules": {
                "mentor_kali_devtools": {
                    "found": self.module_loader.module_exists("mentor_kali_devtools"),
                    "loaded": "mentor_kali_devtools" in self.active_modules,
                    "enabled": bool(self.config["mentor_mode"]),
                }
            },
        }

    async def get_config(self) -> Dict[str, Any]:
        return self.config

    async def update_config(self, cfg: Dict[str, Any]) -> None:
        self.config.update(cfg)
        if "mentor_mode" in cfg:
            self.active_modules = self.module_loader.load_enabled(
                ["mentor_kali_devtools"] if self.config["mentor_mode"] else []
            )
