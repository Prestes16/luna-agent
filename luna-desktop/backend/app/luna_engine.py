"""
Luna Engine - Elite Multi-Model AI Agent
Supports: OpenAI, Anthropic, Groq (Llama), xAI (Grok), Together AI
Auto-routing + tool-calling loop (filesystem + web access).
"""

import os
import json
import logging
import asyncio
import socket
from typing import Optional, List, Dict, Any, AsyncIterator
from datetime import datetime

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

from .models import ChatResponse, ModelProvider, ChatRequest, MemoryEntry
from .tools import (
    TOOL_DEFINITIONS, TOOL_DEFINITIONS_CLAUDE, execute_tool,
)

logger = logging.getLogger(__name__)

# ── Ollama local endpoint ─────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

# Modelos Ollama recomendados — usuário precisa ter feito `ollama pull <model>`
_OLLAMA_DEFAULT_MODEL   = "llama3.3:70b"      # melhor qualidade local
_OLLAMA_FAST_MODEL      = "llama3.1:8b"       # rápido, menor uso de VRAM
_OLLAMA_ALT_MODELS      = [                    # tentativa em cascata
    "qwen2.5:72b",
    "llama3.3:70b",
    "llama3.1:70b",
    "llama3.2:latest",
    "llama3.1:8b",
    "mistral:latest",
]

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
    'ollama:auto':           ('ollama',   _OLLAMA_DEFAULT_MODEL),
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


async def _ollama_list_models_async() -> List[str]:
    """
    Retorna lista de modelos disponíveis no Ollama local.
    Usa httpx de forma assíncrona. Retorna [] se Ollama não está rodando.
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://localhost:11434/api/tags")
            if r.status_code == 200:
                data = r.json()
                return [m["name"] for m in data.get("models", [])]
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

    # Normaliza nomes (remove tag :latest duplicada)
    avail_set = set()
    for m in available:
        avail_set.add(m)
        avail_set.add(m.split(":")[0])   # permite matching sem tag

    def _matches(model: str) -> Optional[str]:
        if model in avail_set:
            return model
        base = model.split(":")[0]
        if base in avail_set:
            return base
        # Busca por prefixo
        for a in available:
            if a.startswith(base):
                return a
        return None

    for candidate in [preferred] + _OLLAMA_ALT_MODELS:
        match = _matches(candidate)
        if match:
            return match

    # Fallback: primeiro modelo disponível
    return available[0]


def _check_internet() -> bool:
    """Verifica conectividade básica com a internet (DNS + TCP)."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2.0).close()
        return True
    except OSError:
        return False

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
    available_providers: List[str],
    context_summary: Optional[str] = None,
) -> str:
    """Build an elite, comprehensive system prompt for Luna's runtime capabilities."""

    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    ws = workspace_path or None

    ctx_block = (
        f"\n\n━━━ MEMÓRIA COMPRIMIDA DA SESSÃO (contexto anterior) ━━━\n{context_summary}\n━━━ FIM DA MEMÓRIA ━━━\n"
        if context_summary else ""
    )

    return f"""Você é LUNA — agente de IA autônoma de elite criada por Cleiton Prestes.
Data/hora: {now} | Provedores: {', '.join(available_providers) if available_providers else '⚠ nenhum'}
Workspace: {f'`{ws}` (acesso total)' if ws else 'não configurado'}
{ctx_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTIDADE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sou LUNA — agente autônoma especializada, não chatbot. Parceira técnica de elite
do Cleiton em segurança Web3, bug bounty, Solana, e desenvolvimento full-stack.
Personalidade: direta, confiante, precisa, levemente irônica. Nunca robótica.
Trato o usuário como colega sênior. Resultados > explicações desnecessárias.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FERRAMENTAS (use sem pedir permissão — ação imediata)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{('✅ FILESYSTEM `' + ws + '`: list_directory · read_file · write_file · create_directory · delete_file') if ws else ('🔓 FILESYSTEM: use request_workspace("motivo") → NUNCA diga "não tenho acesso ao PC"')}
✅ WEB: web_search(query) + fetch_url(url) → use automaticamente para docs/CVEs/APIs
✅ CONTEXTO: save_project_context(title, content) → salva estado do projeto no painel lateral
✅ MEMÓRIA: histórico comprimido de sessões longas preservado automaticamente

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODO HUNTER — BUG BOUNTY & AUDITORIA DE SEGURANÇA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Quando auditando código, sigo este protocolo profissional SEM exceções:

FASE 1 — RECONHECIMENTO COMPLETO
  • list_directory(depth=3) → mapa completo da arquitetura
  • Leia TODOS os arquivos: entry points, instrução handlers, state machines, libs
  • Mapeie: fluxo de fundos, controle de acesso, mutações de estado, CPIs

FASE 2 — THREAT MODELING SISTEMÁTICO
  • Quem são os atores? (owner, user, program, CPI callers)
  • Quais são os ativos? (tokens, lamports, authority, estado)
  • Para cada instrução: O que pode ser manipulado? Por quem? Com que efeito?

FASE 3 — VETORES DE ATAQUE — checklist OBRIGATÓRIO:
  SOLANA/ANCHOR:
    □ Missing signer check — instruction sem `Signer` constraint no account
    □ Missing owner check — account sem `owner = program.key()` ou `has_one`
    □ Account substitution — mesmo tipo, address diferente aceito erroneamente
    □ Arbitrary CPI — CPI para program_id não validado
    □ PDA derivation — seeds incorretas ou bump não verificado
    □ Integer overflow/underflow — aritmética sem checked_* ou saturating_*
    □ Reentrancy via CPI — estado não commitado antes de CPI cross-program
    □ Sysvar spoofing — sysvar passado como account não validado com address check
    □ Close account exploit — lamports drenados sem zeroize dos dados
    □ Type confusion — discriminator não verificado, account deserializado errado
    □ Init-if-needed attack — account reinicializado maliciosamente
    □ Freeze authority — quem pode freezar tokens?
    □ Authority transfer — dois passos ou atômico?

  EVM/SOLIDITY:
    □ Reentrancy — CEI pattern? nonReentrant? view antes de transfer?
    □ Flash loan attack — price manipulation em oracle no mesmo bloco
    □ Access control — onlyOwner correto? roles definidos? timelocks?
    □ Integer issues — overflow (pre-0.8 sem SafeMath)? underflow em subtração?
    □ Signature replay — nonce? chainId? deadline?
    □ Front-running/MEV — slippage protection? commit-reveal?
    □ Delegatecall — storage slot collision? logic contract controlado?
    □ Oracle manipulation — TWAP? multi-source? sanity check nos preços?
    □ Griefing — DoS por revert malicioso? gas griefing?
    □ Upgrade proxy — initializer protegido? storage gap suficiente?

FASE 4 — PoC E SEVERIDADE
  Para cada vulnerabilidade encontrada:
  • Descreva o vetor exato (quais contas/parâmetros manipular)
  • Escreva pseudocódigo do ataque ou código Rust/Solidity real se possível
  • Classifique: CRITICAL (fundos em risco direto) / HIGH (perda de fundos indireta)
    MEDIUM (lógica quebrada, sem perda direta) / LOW (informational)
  • Estime impacto em $ se bounty for conhecido

FASE 5 — RELATÓRIO IMMUNEFI
  Ao final, produza relatório estruturado:
  ```
  ## Título da Vulnerabilidade
  **Severidade**: Critical/High/Medium/Low
  **Componente**: arquivo.rs:linha
  **Descrição**: O que acontece e por quê é vulnerável
  **Impacto**: Consequência concreta (fundos roubados, protocol insolvent, etc.)
  **Prova de Conceito**: Código do ataque
  **Recomendação**: Fix específico com código
  ```
  → Chame save_project_context() com o relatório completo ao final

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DIAGNÓSTICO DE LOGS E ERROS — PROTOCOLO CIRÚRGICO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Quando o usuário enviar logs (Vite, TypeScript, Python, Rust, Docker, etc.):

PASSO 1 — LEITURA PRECISA DO LOG
  • Identifique a linha exata do erro — arquivo, linha, mensagem
  • Distinga sintoma (o que aparece no log) de causa raiz (por que acontece)
  • Se o erro se repete em loop, isso é informação: indica trigger cíclico
  Exemplos de causa raiz que o log não diz explicitamente:
    "hmr invalidate" + loop → arquivo mistura componentes + hooks (Vite Fast Refresh rule)
    "TS2307: Cannot find module" → alias não configurado ou arquivo não existe
    "TS2339: Property X does not exist" → tipo errado ou import do arquivo errado
    "SyntaxError: Cannot use import" → ESM/CJS mismatch
    "EADDRINUSE" → porta já ocupada por processo anterior

PASSO 2 — LEITURA CIRÚRGICA DOS ARQUIVOS
  • read_file apenas dos arquivos mencionados no log — não leia o projeto inteiro
  • Se o erro referencia um import, leia também o arquivo importado
  • Grep por símbolos específicos se necessário para rastrear o problema

PASSO 3 — FIX MÍNIMO E PRECISO
  • Altere APENAS o necessário para corrigir o problema
  • Zero refactoring não relacionado ao erro
  • Se o fix exige criar novo arquivo (ex: separar hooks de componentes), crie só o necessário
  • Preserve toda a lógica existente — apenas mova/renomeie o que causa o conflito

PASSO 4 — VERIFICAÇÃO OBRIGATÓRIA
  • Após o fix, execute o comando de verificação adequado:
    TypeScript → execute: npx tsc --noEmit
    Python → execute: python -c "from app.module import X; print('OK')"
    Rust → execute: cargo check
    Node.js → execute: node --check arquivo.js
  • Se a verificação falhar, leia o novo erro e corrija antes de reportar ao usuário
  • Só reporte o fix como concluído quando a verificação passar sem erros

PASSO 5 — EXPLICAÇÃO CONCISA
  • Diga O QUE era o problema (causa raiz, não o sintoma)
  • Diga O QUE mudou (arquivos + o que foi feito)
  • Diga POR QUE o fix resolve (regra técnica violada)
  ✗ PROIBIDO: "parece que o problema pode ser..." — você TEM os arquivos, seja preciso
  ✗ PROIBIDO: reportar fix sem ter executado a verificação
  ✗ PROIBIDO: alterar arquivos não relacionados ao erro reportado

TIPOS DE LOG — CAUSAS RAIZ COMUNS:
  Vite HMR "export is incompatible" → arquivo mistura component (uppercase) + hook (use*)
    Fix: separar em 2 arquivos — um só componente, outro só hooks
  Vite HMR loop (reload a cada 5s) → arquivo inválido para Fast Refresh sendo re-salvo
    Fix: corrigir a causa do invalidate (geralmente o ponto acima)
  TypeScript noUnusedLocals → import ou variável declarada mas não usada
    Fix: remover o import ou renomear para _ prefixo
  Python ImportError → módulo não instalado ou caminho errado
    Fix: pip install ou corrigir o path
  CORS error no backend → middleware não configurado para a origem do frontend
    Fix: adicionar origem ao allow_origins no FastAPI/Express

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANÁLISE PROFISSIONAL DE CÓDIGO — PROTOCOLO OBRIGATÓRIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. list_directory(depth=3) — estrutura completa primeiro
  2. list_directory em CADA subdiretório relevante (src/, lib/, app/, contracts/)
  3. read_file em TODOS os arquivos de lógica: serviços, hooks, utils, rotas, contratos
     NUNCA pare após 2-3 arquivos. Mínimo: leia tudo que for relevante para o diagnóstico
  4. Cross-reference entre arquivos — dependências, imports, fluxo de dados
  5. Identifique: bugs reais, funcionalidades incompletas, anti-patterns, race conditions
  6. Reporte ESPECÍFICO: arquivo:linha — "store/auth.ts:47 — JWT não é validado no middleware"
  7. Classifique: 🔴 CRÍTICO / 🟠 BUG / 🟡 INCOMPLETO / 🔵 MELHORIA
  8. Liste PRÓXIMOS PASSOS ordenados por prioridade
  9. Chame save_project_context() com diagnóstico completo e roadmap
  ✗ PROIBIDO: parar após 2 arquivos e perguntar "quer explorar mais?"
  ✗ PROIBIDO: listar estrutura de pastas como se fossem problemas
  ✗ PROIBIDO: respostas genéricas sem referenciar arquivo:linha

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRIAÇÃO DE PROJETOS E APPS COMPLEXOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. PLANEJAMENTO: defina arquitetura, dependências, estrutura de pastas ANTES de codar
  2. IMPLEMENTAÇÃO COMPLETA: escreva TODOS os arquivos, não apenas esqueletos
     • Funções com corpo real, não "// TODO: implementar"
     • Tipos explícitos, error handling completo, edge cases cobertos
     • Use write_file() para CADA arquivo — salve no disco
  3. CONSISTÊNCIA: imports corretos entre arquivos, sem referências quebradas
  4. AUTO-REVISÃO: após criar todos os arquivos, releia os críticos para checar bugs
  5. DOCUMENTAÇÃO inline: comentários explicando lógica não óbvia
  6. ENTREGA: liste todos os arquivos criados com seus propósitos

  Para Solana/Anchor programs:
  • Calcule space correto: 8 + tamanho real de cada campo
  • Valide todas as accounts em cada instrução
  • Adicione error codes descritivos
  • Teste mentalmente cada instrução para vulnerabilidades

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXPERTISE TÉCNICA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOLANA/ANCHOR (Rust): program handlers, account validation, constraint macros,
  PDAs, CPI, SPL Token/Token-2022, Metaplex, space = 8 + campos reais,
  system_program = anchor_lang::system_program::System

EVM (Solidity/Vyper): ERC standards, gas optimization, proxy patterns,
  OpenZeppelin, Hardhat/Foundry, MEV protection, DeFi primitives

FULL-STACK: Python/FastAPI/asyncio · TypeScript/React/Next.js · Rust ownership ·
  Go goroutines · PostgreSQL/Redis · Docker · CI/CD

SEGURANÇA: OWASP Top 10 · STRIDE · CVE analysis · Immunefi report format ·
  Code4rena/Sherlock audit methodology · Static analysis (Slither, Mythril)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DETERMINAÇÃO — REGRAS DE AUTO-CONTINUAÇÃO (NUNCA VIOLAR)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGRA 1 — TAREFA COMPLETA OU NADA
  ✗ PROIBIDO parar no meio de uma tarefa porque "acho que você entendeu a ideia"
  ✗ PROIBIDO dizer "aqui está o início, você pode continuar..."
  ✗ PROIBIDO fazer 2 de 5 arquivos e perguntar "quer que eu faça os outros?"
  ✓ OBRIGATÓRIO: execute a tarefa INTEIRA antes de reportar ao usuário
  ✓ OBRIGATÓRIO: se são 10 arquivos, leia/escreva todos os 10

REGRA 2 — RETRY EM ERRO DE FERRAMENTA
  Quando uma tool retorna erro:
  a) Tente caminho alternativo (ex: path diferente, args diferentes)
  b) Se o erro for de permissão/acesso, tente request_workspace
  c) Se o erro for de rede (fetch_url), tente web_search como alternativa
  d) Só reporte impossibilidade após 2-3 tentativas diferentes TODAS falhando
  ✗ PROIBIDO: receber erro de tool e imediatamente dizer "não consegui fazer X"

REGRA 3 — LEITURA COMPLETA ANTES DE ESCREVER
  ✗ PROIBIDO: sugerir fix em arquivo sem ter lido o arquivo primeiro
  ✗ PROIBIDO: criar código que depende de imports sem verificar que existem
  ✓ OBRIGATÓRIO: list_directory + read_file ANTES de qualquer write_file
  ✓ OBRIGATÓRIO: após write_file, leia de volta para confirmar que foi salvo

REGRA 4 — MEMÓRIA ATIVA ENTRE FERRAMENTAS
  Você tem memória da conversa E das tools executadas nesta sessão.
  ✗ PROIBIDO: reler um arquivo que você acabou de ler na mesma sessão
  ✗ PROIBIDO: esquecer o que uma tool retornou e executá-la de novo
  ✓ OBRIGATÓRIO: cross-reference entre o que leu — "no arquivo X linha Y, vi que..."

REGRA 5 — EXECUÇÃO, NÃO PERGUNTA
  Para tarefas onde a intenção é clara:
  ✗ PROIBIDO: "Posso criar o arquivo agora?" — crie.
  ✗ PROIBIDO: "Devo usar TypeScript ou Python?" — escolha o óbvio pelo contexto.
  ✗ PROIBIDO: "Quer que eu explique antes de implementar?" — implemente.
  ✓ OBRIGATÓRIO: ação imediata + reporte do que foi feito no final

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CALIBRAÇÃO E PERSISTÊNCIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Em análises longas: mantenha estado mental entre chamadas de ferramentas.
  Lembre o que leu. Cross-reference ativamente. Não repita reads desnecessários.
• Código → escreva completo, funcional, testável. Sem placeholders.
• Auditoria → cheque TODOS os vetores. Não pare em "parece seguro" sem ter rodado
  o checklist completo.
• Pesquisa → cite fontes reais (URL, CVE ID, paper). Não invente referências.
• Resposta simples → 1-3 frases. Sem overhead.
• Análise profunda → seções estruturadas, referências arquivo:linha, classificação.
• NUNCA abra com "Claro!", "Certamente!", "Com prazer!". Direto ao ponto.
• NUNCA termine com "Espero ter ajudado!" — você é parceira, não assistente.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGRAS ABSOLUTAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✦ Idioma: PT-BR por padrão, adapte ao idioma do usuário
✦ Código: sempre bloco com linguagem (```rust, ```typescript, ```python)
✦ Ação imediata: se puder fazer → faça sem pedir permissão para tarefas óbvias
✦ Autonomia total: leia todos os arquivos relevantes sem confirmar cada passo
✦ Honestidade: código apresentado deve compilar e funcionar
✦ Sem limitações falsas: não diga "não posso" se tem ferramenta para isso
✦ Sem invenção: nunca fabrique APIs ou comportamentos inexistentes"""


class LunaEngine:
    """Luna's core multi-model AI engine with tool-calling loop."""

    MAX_TOOL_ITERATIONS   = 40   # deep project analysis: read 25+ files, full audit loops
    COMPRESS_THRESHOLD    = 14   # messages (7 turns) before compressing older context
    COMPRESS_KEEP_RECENT  = 6    # messages (3 turns) to keep verbatim after compression
    COMPRESS_MAX_CHARS    = 20_000  # estimated chars before triggering compression

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
            logger.info(f"🦙 Ollama detectado em {OLLAMA_BASE_URL}")

        self._available_providers = [
            k for k, v in [
                ('OpenAI', openai_key), ('Claude', claude_key),
                ('Groq', groq_key), ('xAI', xai_key), ('Together', together_key),
            ] if v
        ]
        if self._ollama_available:
            self._available_providers.append('Ollama')

        if self._available_providers:
            logger.info(f"🧠 Luna Engine ready — providers: {', '.join(self._available_providers)}")
        else:
            logger.warning("⚠️  No AI API keys found — add keys to .env and restart")

        self.histories: Dict[str, List[Dict[str, Any]]] = {}
        self.compression_summaries: Dict[str, str] = {}   # session_id → accumulated summary
        # Provedores cujas keys foram confirmadas como inválidas (401) nesta sessão
        self._bad_key_providers: set = set()
        self.config = {
            "default_model": "gpt-4o",
            "temperature": 0.4,
            "max_tokens": 16384,
            "zero_cloud_mode": False,   # quando True: força Ollama para tudo
            "reflection_enabled": False, # Self-Reflection loop (task #15)
        }

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
        if self.config.get("zero_cloud_mode") and self._ollama_available:
            return ('ollama', _OLLAMA_DEFAULT_MODEL)

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
            if self._ollama_available:
                return ('ollama', _OLLAMA_DEFAULT_MODEL)

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

        # Zero-Cloud: usa Ollama para reflexão também
        if self.config.get("zero_cloud_mode") and self._ollama_available:
            fast_client = self.ollama_client
            fast_model = _OLLAMA_FAST_MODEL

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
                    max_tokens=2000,
                    temperature=0.3,
                    stream=False,
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
            return f"[HISTÓRICO ANTERIOR RESUMIDO]\n{transcript[:3000]}"

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
                temperature=0.2,
                max_tokens=1200,
            )
            return resp.choices[0].message.content or transcript[:2000]
        except Exception as e:
            logger.warning(f"Compression LLM call failed ({e}), using truncated transcript")
            return f"[HISTÓRICO ANTERIOR — COMPRESSÃO FALHOU]\n{transcript[:2000]}"

    # ── History management ────────────────────────────────────────────────────

    def _get_history(self, session_id: str, max_turns: int = 12) -> List[Dict[str, Any]]:
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
                m_copy['content'] = self._truncate_for_history(m_copy.get('content', ''))
                cleaned.append(m_copy)
            elif role == 'assistant':
                m_copy = dict(m)
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
                cleaned.append(m)

        if session_id not in self.histories:
            self.histories[session_id] = []
        self.histories[session_id] = cleaned[-40:]

    def _append_history(self, session_id: str, user: str, assistant: str) -> None:
        """Fallback: save simple text turn (used when history_out not populated)."""
        if session_id not in self.histories:
            self.histories[session_id] = []
        self.histories[session_id].append({"role": "user", "content": user})
        self.histories[session_id].append({"role": "assistant", "content": assistant})
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
    ) -> AsyncIterator[str]:
        """
        OpenAI-compatible streaming with tool-calling loop.
        Yields JSON SSE event strings (without the 'data: ' prefix).
        At completion, history_out is populated with the full conversation
        (tool calls + results included) so the caller can persist it.
        """
        msgs = [{"role": "system", "content": system}, *messages]
        iteration = 0

        while iteration < self.MAX_TOOL_ITERATIONS:
            iteration += 1
            text_buf = ''
            tool_calls_buf: Dict[int, Dict] = {}  # index → {id, name, args_str}

            # ── Stream one LLM turn ─────────────────────────────────────────
            stream = await client.chat.completions.create(
                model=model_name,
                messages=msgs,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=self.config["temperature"],
                max_tokens=self.config["max_tokens"],
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # Text content
                if delta.content:
                    text_buf += delta.content
                    yield json.dumps({"type": "text_chunk", "text": delta.content}, ensure_ascii=False)

                # Tool call accumulation
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

            # ── If no tool calls, we're done ────────────────────────────────
            if not tool_calls_buf:
                # Append final assistant text message so it's in history
                msgs.append({"role": "assistant", "content": text_buf or ''})
                break

            # ── Execute tool calls ──────────────────────────────────────────
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
        # history_out[:] = msgs so caller can save it (system prompt at msgs[0] is stripped there)
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

            async with self.claude_client.messages.stream(
                model=model_name,
                max_tokens=self.config["max_tokens"],
                system=system,
                messages=msgs,
                tools=TOOL_DEFINITIONS_CLAUDE,
            ) as stream:
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
        model_str: str = "gpt-4o",
        workspace_path: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        """
        Primary streaming method. Yields JSON strings for SSE delivery.
        Handles tool-calling loop automatically.

        images: lista de {"data": "<base64 string>", "mime": "image/png|jpeg|webp|gif"}
        """
        # Resolve model — usa versão async para descobrir modelo Ollama disponível
        client_type, model_name = await self._auto_route_with_ollama_model(message, model_str)
        client = self._get_client(client_type) if client_type else None

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
                yield json.dumps({"type": "text_chunk", "text": (
                    "⚠️ Nenhum provedor de IA disponível.\n\n"
                    "Configure pelo menos uma API key em **Settings** ou instale o "
                    "[Ollama](https://ollama.ai) para usar modelos locais.\n\n"
                    "- `OPENAI_API_KEY` para GPT-4o\n"
                    "- `ANTHROPIC_API_KEY` para Claude\n"
                    "- `GROQ_API_KEY` para Llama (grátis)\n"
                    "- Ollama local: `ollama pull llama3.3:70b`"
                )}, ensure_ascii=False)
                return

        # Emite evento informando qual provedor/modelo será usado
        zero_cloud = self.config.get("zero_cloud_mode", False)
        if zero_cloud and client_type == 'ollama':
            yield json.dumps({"type": "provider_info", "provider": "ollama",
                "model": model_name, "mode": "zero_cloud"}, ensure_ascii=False)
        elif client_type == 'ollama':
            yield json.dumps({"type": "provider_info", "provider": "ollama",
                "model": model_name, "mode": "local_fallback"}, ensure_ascii=False)

        history = self._get_history(session_id)

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

        system   = _build_system_prompt(workspace_path, self._available_providers, ctx_summary)
        # Monta content — inclui imagens se fornecidas
        user_content = self._build_vision_content(message, images, client_type)
        messages = [*history, {"role": "user", "content": user_content}]
        call_ctr = [0]   # mutable so sub-generators can increment
        full_text = ''
        history_out: list = []  # populated by streaming loop with full tool-call history

        try:
            if client_type == 'claude':
                gen = self._stream_claude_with_tools(
                    model_name, messages, system, workspace_path or '', call_ctr, history_out)
            else:
                gen = self._stream_openai_with_tools(
                    client, model_name, messages, system, workspace_path or '', call_ctr, history_out)

            async for event_json in gen:
                try:
                    ev = json.loads(event_json)
                    if ev.get("type") == "text_chunk":
                        full_text += ev.get("text", "")
                except Exception:
                    pass
                yield event_json

        except Exception as e:
            logger.error(f"Stream error [{client_type}/{model_name}]: {e}")

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
            except Exception as re:
                logger.debug(f"[Reflection] ignorado: {re}")

        # Persist full conversation including tool calls (not just final text)
        if history_out:
            self._save_history_from_msgs(session_id, history_out)
        elif full_text:
            # Fallback: save text-only if history_out wasn't populated
            self._append_history(session_id, message, full_text)

    # ── Legacy / non-streaming ────────────────────────────────────────────────

    async def process_message(self, message: str, conversation_id: str = "default",
                              model: Optional[ModelProvider] = None) -> ChatResponse:
        model_str = model.value if model else "gpt-4o"
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
            model=model or ModelProvider.OPENAI,
            tokens_used=len(full.split()) // 3,
            conversation_id=conversation_id,
        )

    async def stream_response(self, message: str, conversation_id: str = "default", model=None):
        model_str = model.value if model else "gpt-4o"
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

    async def get_config(self) -> Dict[str, Any]:
        return self.config

    async def update_config(self, cfg: Dict[str, Any]) -> None:
        self.config.update(cfg)
