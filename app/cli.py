"""
Luna Agent - Interface Terminal v2.2
====================================
Cérebro estratégico completo:
  - Classificação automática de tarefas
  - Planejamento explícito antes de agir (Think → Plan → Act)
  - Reflexão e aprendizado pós-execução
  - Memória de contexto de projetos
  - 15 ferramentas: filesystem, shell, web search, aprendizado
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from app.models import AgentConfig
from app.runtime import AgentRuntime
from app.state_store import load_config, ensure_workspace
from app.services.memory import stm_add, stm_get
from app.tools.filesystem_tool import FilesystemTool
from app.strategy import StrategyEngine, get_strategy_engine, TaskClassification

# Multi-LLM router e audit engine — importação lazy para não quebrar se deps ausentes
try:
    from app.llm_router import get_router as _get_luna_router, LunaLLMRouter  # noqa: F401
    _LUNA_ROUTER_AVAILABLE = True
except ImportError:
    _LUNA_ROUTER_AVAILABLE = False

try:
    from app.core.audit_engine import AuditEngine
    _AUDIT_AVAILABLE = True
except ImportError:
    _AUDIT_AVAILABLE = False

try:
    from app.hunter.hunter_engine import get_hunter_engine, HuntConfig, HuntMode
    from app.hunter.grains_manager import get_grains_manager
    _HUNTER_AVAILABLE = True
except ImportError:
    _HUNTER_AVAILABLE = False


logger = logging.getLogger("luna.cli")


# ─── System Prompt Base ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """Você é a Luna — agente autônoma de engenharia e segurança de elite para o Cleiton.

Cleiton trabalha com: Python, Rust, TypeScript, Solidity, Solana (Anchor), Web3 security, bug bounty (Immunefi).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTIDADE E MODO DE OPERAÇÃO:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Você é uma agente de execução — não um chatbot.
Quando receber uma tarefa, sua resposta padrão é AGIR, não explicar o que vai fazer.

REGRAS ABSOLUTAS — VIOLAÇÃO = FALHA DE EXECUÇÃO:
1. NUNCA diga "não posso acessar/ler/criar/executar". Você TEM as ferramentas. Use-as.
2. NUNCA invente conteúdo de arquivo. Leia primeiro com scan_project ou read_file.
3. NUNCA dê análise genérica. Todo dado deve vir de arquivo REAL lido por você.
4. NUNCA pare no scan_project — é o passo 1, não o último. Siga com read_many
   e depois com run_command("grep -rn ...") para busca no projeto inteiro.
5. NUNCA use grep_file em um único arquivo quando o projeto inteiro pode ser buscado
   com run_command("grep -rn 'padrão' --include='*.ext' .", cwd=path).
6. NUNCA aplique padrões de Rust/Solana em projeto TypeScript/Python (e vice-versa).
   Detecte a stack no passo 1 e adapte os padrões de busca ao tipo de projeto.
7. SEMPRE chame save_context após entender um projeto.
8. SEMPRE chame learn_lesson() como PENÚLTIMA ação. Sem learn_lesson = incompleto.
9. NUNCA use frases de filler: "estou à disposição", "posso ajudar", "se precisar
   de mais", "fico feliz em", "espero ter ajudado". Resposta direta, técnica, sem cortesia vazia.
   Você é uma agente de elite — fale como uma, não como um chatbot.
10. NUNCA afirme CVEs sem verificar a fonte. Quando web_search retornar CVEs:
    → Mencione apenas CVEs com ano plausível (não futuros como 2026+)
    → Use linguagem cautelosa: "CVE-XXXX-YYYY reportado em [fonte]"
    → Se a fonte não confirmar claramente, diga "vulnerabilidade similar a..." sem citar CVE
    → CVE inventado é pior que nenhum CVE.
11. OBRIGATÓRIO MOSTRAR ACHADOS NA RESPOSTA FINAL:
    → NUNCA diga apenas "análise concluída", "tarefa executada", "feito com sucesso" sem mostrar o que encontrou.
    → Sua resposta DEVE conter: estrutura real do projeto lida, trechos de código relevantes,
      problemas encontrados com ARQUIVO:LINHA exata, recomendações baseadas em código real.
    → save_context é para CACHE INTERNO — não substitui mostrar os achados ao usuário.
    → Se você leu arquivos, CITE o conteúdo. Se encontrou um bug, MOSTRE o trecho. Se analisou código, EXPONHA os findings.
    → Resposta sem evidências de código real = resposta inválida.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROTOCOLO THINK → PLAN → ACT → REFLECT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{strategic_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAPACIDADES (TODAS REAIS E FUNCIONANDO):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Filesystem: list_dir, read_file, read_file_chunked, write_file, patch_file,
            search_files, grep_file, create_dir, scan_project, read_many
Execução:   run_command (git, npm, cargo, anchor, python, solana-cli, etc.)
Acesso:     allow_dir (libera qualquer diretório do PC em tempo real)
Web:        web_search (documentação, CVEs, writeups, preços)
Memória:    save_context, get_context (persiste fatos sobre projetos na sessão)
Aprendizado: learn_lesson, get_lessons (aprende com execuções anteriores)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DIRETÓRIOS COM ACESSO TOTAL:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{allowed_dirs}

Diretório padrão: {primary_dir}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO DE PROJETOS SALVO:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{project_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESPECIALIZAÇÕES DEEP:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOLANA/ANCHOR — vetores: signer check missing, PDA bump misuse, CPI reentrancy,
  account confusion, arithmetic overflow, missing owner check, account reloading.
  Ferramentas: anchor build/test, solana-test-validator, cargo test.

IMMUNEFI / WEB3 — Solidity: reentrancy, overflow, access control, flash loans.
  Classificação: Critical (fundos em risco) / High / Medium / Low.
  PoC em TypeScript com @coral-xyz/anchor ou ethers.js.

APIs/BACKEND — JWT/OAuth falhos, SQLi/NoSQLi, SSRF, IDOR, lógica de negócios.

Responda SEMPRE em português. Execute sem hesitar.
"""

# ─── LunaConsole ─────────────────────────────────────────────────────────────

class LunaConsole:
    def __init__(self):
        self.console = Console(force_terminal=True, width=120)
        self.session_id = "default"
        self.config = load_config()
        self.runtime = AgentRuntime(self.config)
        self.fs = FilesystemTool(self._get_allowed_dirs())
        self.strategy = get_strategy_engine("data")
        # Memória de contexto de projetos (persiste durante a sessão)
        self._project_context: dict[str, str] = {}

    def _get_allowed_dirs(self) -> list[str]:
        from_env = os.getenv("LUNA_ALLOWED_DIRS", "")
        if from_env:
            return [d.strip() for d in from_env.split(",") if d.strip()]
        dirs = list(self.config.safe_base_dirs or [])
        if self.config.target_root:
            dirs.append(self.config.target_root)
        for d in ["/mnt/d", "/mnt/c", str(Path.home())]:
            if Path(d).exists() and d not in dirs:
                dirs.append(d)
        return dirs or [str(Path.home())]

    def print_header(self) -> None:
        stats = self.strategy.get_stats()
        lessons_info = f" | {stats['total_lessons']} lições" if stats.get("total_lessons") else ""
        self.console.print(Text(f"🌙 LUNA AGENT v2.2{lessons_info}", style="bold cyan"))
        self.console.print("[dim]Think → Plan → Act → Reflect | Solana · Web3 · Bug Bounty[/dim]")
        dirs = " | ".join(str(d) for d in self.fs.allowed_dirs[:3])
        if len(self.fs.allowed_dirs) > 3:
            dirs += f" +{len(self.fs.allowed_dirs) - 3} mais"
        self.console.print(f"[dim]Acesso: {dirs}[/dim]")
        self.console.print()

    def print_help(self) -> None:
        self.console.print("""[bold cyan]Comandos:[/bold cyan]
  /allow <path>        - Libera acesso a qualquer diretório
  /dirs                - Lista diretórios com acesso
  /ls <path>           - Lista conteúdo de pasta
  /cat <path>          - Lê arquivo
  /run <cmd>           - Executa comando shell
  /scan <path>         - Analisa projeto completo
  /audit <path>        - Auditoria estática rápida (Solana/EVM — sem LLM)

[bold cyan]🎯 Hunter-V2 Elite (Bug Bounty):[/bold cyan]
  /hunt <path>         - Auditoria completa: Triage→Deep Audit→PoC→Relatório Immunefi
  /hunt <sig>          - Analisa transação on-chain via Helius RPC
  /hunt --live         - Monitora Mainnet em tempo real (LaserStream)
  /hunt --deep <path>  - Força deep audit com Llama-3.1-405B sem confirmar
  /generate-poc <path> - Gera PoC para findings existentes em LUNA_SECURITY_REPORT.md
  /report-format <path>- Formata relatório de auditoria no padrão Immunefi
  /grains              - Saldo e histórico de Luna Grains (custo de tokens)
  /grains topup <n>    - Adiciona N Grains ao saldo

  /ctx                 - Mostra contexto de projetos
  /ctx clear           - Limpa contexto
  /learn               - Mostra lições aprendidas
  /stats               - Estatísticas de aprendizado
  /router              - Status dos provedores LLM
  /router reset        - Reseta falhas de provedores
  /config              - Configuração atual
  /help                - Ajuda
  /exit                - Sair

[dim]Converse normalmente — Luna planeja e executa automaticamente.[/dim]
  Exemplos:
    "analise o projeto em C:\\Dev\\meu-app e diga o que falta"
    "encontre vulnerabilidades no programa Solana em programs/vault"
    /hunt C:\\Dev\\bags-shield
    /hunt 3KpZ9rVm...signature
    /hunt --live --program So11...
""")

    def p(self, *args, **kwargs):
        self.console.print(*args, **kwargs)

    def err(self, msg: str):
        self.console.print(f"[bold red]✗ {msg}[/bold red]")

    def ok(self, msg: str):
        self.console.print(f"[bold green]✓ {msg}[/bold green]")

    def msg_user(self, content: str):
        self.console.print(f"\n[bold cyan]You:[/bold cyan] {content}")

    def msg_luna(self, content: str):
        self.console.print(f"\n[bold magenta]Luna:[/bold magenta]")
        self.console.print(Panel(content, border_style="magenta", padding=(0, 2)))

    def thinking(self, msg: str):
        self.console.print(f"[dim yellow]◎ {msg}[/dim yellow]")

    def tool_call(self, n: int, name: str, args_summary: str):
        self.console.print(f"[yellow]  ⚙ [{n}] {name}({args_summary})[/yellow]")

    def prompt(self) -> str:
        return self.console.input("\n[bold cyan]> [/bold cyan]")

    def get_project_context_str(self) -> str:
        if not self._project_context:
            return "(Nenhum contexto salvo ainda)"
        parts = []
        for key, val in self._project_context.items():
            parts.append(f"[{key}]\n{val}")
        return "\n\n".join(parts)

    def save_context(self, key: str, value: str) -> None:
        self._project_context[key] = value
        logger.info(f"Contexto salvo: {key} ({len(value)} chars)")

    def get_context(self, key: str) -> str | None:
        return self._project_context.get(key)


# ─── LunaCLI ─────────────────────────────────────────────────────────────────

class LunaCLI:
    def __init__(self):
        self.c = LunaConsole()
        self.running = True

    def run(self) -> None:
        ensure_workspace()
        self.c.print_header()
        self.c.print_help()
        while self.running:
            try:
                user_input = self.c.prompt()
                if not user_input.strip():
                    continue
                self.handle(user_input.strip())
            except KeyboardInterrupt:
                self.c.ok("\nAté logo!")
                self.running = False
            except Exception as e:
                self.c.err(f"Erro inesperado: {e}")
                logger.exception("Erro no loop principal")

    def handle(self, inp: str) -> None:
        if inp.startswith("/"):
            self._cmd(inp)
        else:
            self._chat(inp)

    # ── Comandos ─────────────────────────────────────────────────────────

    def _cmd(self, inp: str) -> None:
        parts = inp.split(maxsplit=1)
        cmd = parts[0].lstrip("/").lower()
        arg = parts[1] if len(parts) > 1 else ""

        match cmd:
            case "help":
                self.c.print_help()

            case "allow":
                if not arg:
                    self.c.err("Uso: /allow <caminho>  ex: /allow /mnt/d/Dev")
                    return
                path = self._win_to_wsl(arg)
                result = self.c.fs.allow_dir(path)
                if "error" in result:
                    self.c.err(result["error"])
                else:
                    self.c.ok(f"Acesso liberado: {result['allowed']}  (total: {result['total']} dirs)")
                    self._persist_allowed_dirs()

            case "dirs":
                self.c.p("[bold cyan]Diretórios com acesso:[/bold cyan]")
                for d in self.c.fs.allowed_dirs:
                    exists = "✓" if Path(d).exists() else "✗"
                    color = "green" if Path(d).exists() else "red"
                    self.c.p(f"  [{color}]{exists}[/{color}] {d}")

            case "ls":
                if not arg:
                    self.c.err("Uso: /ls <caminho>")
                    return
                result = self.c.fs.list_dir(self._win_to_wsl(arg))
                self._print_ls(result)

            case "cat":
                if not arg:
                    self.c.err("Uso: /cat <caminho>")
                    return
                result = self.c.fs.read_file(self._win_to_wsl(arg))
                if "error" in result:
                    self.c.err(result["error"])
                else:
                    ext = Path(arg).suffix.lstrip(".")
                    try:
                        self.c.console.print(
                            Syntax(result["content"], ext or "text", theme="monokai", line_numbers=True)
                        )
                    except Exception:
                        self.c.p(Panel(result["content"], title=arg))

            case "run":
                if not arg:
                    self.c.err("Uso: /run <comando>")
                    return
                result = self.c.fs.run_command(arg)
                self._print_run(result)

            case "scan":
                if not arg:
                    self.c.err("Uso: /scan <caminho>")
                    return
                self.c.thinking("Escaneando projeto...")
                result = self.c.fs.scan_project(self._win_to_wsl(arg))
                if "error" in result:
                    self.c.err(result["error"])
                else:
                    self.c.ok(f"Escaneado: {result['files_read_count']} arquivos em {result['project_root']}")
                    for fname in result["files_read"]:
                        self.c.p(f"  [dim]→ {fname}[/dim]")

            case "ctx":
                if arg.strip().lower() == "clear":
                    self.c._project_context = {}
                    self.c.ok("Contexto limpo.")
                else:
                    self.c.p("[bold cyan]Contexto de Projetos:[/bold cyan]")
                    self.c.p(Panel(self.c.get_project_context_str(), border_style="dim"))

            case "learn":
                lessons = self.c.strategy.load_lessons(limit=10)
                if not lessons:
                    self.c.p("[dim]Nenhuma lição registrada ainda.[/dim]")
                else:
                    self.c.p(f"[bold cyan]📚 Últimas {len(lessons)} lições:[/bold cyan]")
                    for l in lessons:
                        icon = "✅" if l.outcome == "success" else ("⚠️" if l.outcome == "partial" else "❌")
                        self.c.p(f"  {icon} [{l.task_type}] {l.task_summary[:70]}")
                        self.c.p(f"     [dim]✓ {l.what_worked[:80]}[/dim]")

            case "stats":
                stats = self.c.strategy.get_stats()
                t = Table(title="📊 Estatísticas de Aprendizado Luna")
                t.add_column("Tipo de Tarefa")
                t.add_column("Total", justify="right")
                t.add_column("✅ Sucesso", justify="right")
                t.add_column("⚠️ Parcial", justify="right")
                t.add_column("❌ Falhou", justify="right")
                for task_type, data in stats.get("by_type", {}).items():
                    t.add_row(
                        task_type,
                        str(data["total"]),
                        str(data.get("success", 0)),
                        str(data.get("partial", 0)),
                        str(data.get("failed", 0)),
                    )
                self.c.console.print(Panel(t))
                self.c.p(f"[dim]Total: {stats.get('total_lessons', 0)} lições acumuladas[/dim]")

            case "config":
                t = Table(title="Configuração Luna")
                t.add_column("Parâmetro")
                t.add_column("Valor")
                t.add_row("Versão", "2.2")
                t.add_row("Modelo", self.c.config.primary_model)
                t.add_row("Modo", self.c.config.mode)
                t.add_row("Dirs", "\n".join(str(d) for d in self.c.fs.allowed_dirs))
                t.add_row("Contexto", f"{len(self.c._project_context)} entradas")
                t.add_row("Lições", str(self.c.strategy.get_stats().get("total_lessons", 0)))
                self.c.console.print(Panel(t))

            case "audit":
                self._cmd_audit(arg)

            case "hunt":
                self._cmd_hunt(arg)

            case "generate-poc":
                self._cmd_generate_poc(arg)

            case "report-format":
                self._cmd_report_format(arg)

            case "grains":
                self._cmd_grains(arg)

            case "router":
                self._cmd_router(arg)

            case "exit":
                self.running = False
                self.c.ok("Até logo!")

            case _:
                self.c.err(f"Comando desconhecido: /{cmd}  — use /help")

    # ── Chat Principal ────────────────────────────────────────────────────

    def _chat(self, message: str) -> None:
        self.c.msg_user(message)
        stm_add(self.c.session_id, "user", message)

        # ── Fase 1: Classificação estratégica ────────────────────────────
        classification = self.c.strategy.classify(message)
        if classification.needs_planning:
            self.c.thinking(
                f"Tipo: {classification.description} | "
                f"Complexidade: {classification.complexity} | "
                f"Estratégia: {classification.strategy}"
            )

        # ── Carregar lições relevantes ────────────────────────────────────
        lessons_text = self.c.strategy.format_lessons_for_prompt(classification.task_type)

        # ── Construir contexto estratégico ────────────────────────────────
        strategic_context = self.c.strategy.build_thinking_prompt(classification, message)
        if lessons_text:
            strategic_context = lessons_text + "\n\n" + strategic_context

        # ── Montar system prompt completo ─────────────────────────────────
        allowed = ", ".join(str(d) for d in self.c.fs.allowed_dirs)
        primary = str(self.c.fs.allowed_dirs[0]) if self.c.fs.allowed_dirs else "/mnt/d/Dev"
        system = SYSTEM_PROMPT.format(
            strategic_context=strategic_context,
            allowed_dirs=allowed,
            primary_dir=primary,
            project_context=self.c.get_project_context_str(),
        )

        # ── Histórico de conversa ─────────────────────────────────────────
        history = stm_get(self.c.session_id, limit=20)
        messages = [{"role": "system", "content": system}]
        for e in history[:-1]:
            if e.get("role") in ("user", "assistant"):
                messages.append({"role": e["role"], "content": e["content"]})
        messages.append({"role": "user", "content": message})

        self.c.thinking("Executando...")
        start_time = time.time()

        try:
            response, tools_used, success = self._agent_loop(messages, classification)
        except Exception as e:
            response = f"[Erro interno: {e}]"
            tools_used = []
            success = False
            logger.error(f"Erro no chat: {e}", exc_info=True)

        elapsed = time.time() - start_time
        self.c.msg_luna(response)
        stm_add(self.c.session_id, "assistant", response)

        # ── Fase 4: Reflexão e Aprendizado ────────────────────────────────
        if tools_used and classification.needs_planning:
            self.c.thinking(f"Concluído em {elapsed:.1f}s | {len(tools_used)} operações")
            # Auto-salvar lição básica se houve ferramentas usadas
            # (a Luna pode salvar lições mais ricas via learn_lesson tool)
            if success and len(tools_used) >= 2:
                self.c.strategy.save_lesson(
                    task_type=classification.task_type,
                    task_summary=message[:150],
                    what_worked=f"Sequência: {' → '.join(tools_used[:6])}",
                    what_failed="",
                    tools_used=tools_used,
                    outcome="success",
                )

    # ── Loop Agêntico com Estratégia ──────────────────────────────────────

    def _agent_loop(
        self,
        messages: list[dict],
        classification: TaskClassification,
        max_iters: int = 20,
    ) -> tuple[str, list[str], bool]:
        """
        Loop agêntico Think → Plan → Act → Reflect.

        Usa LunaLLMRouter (Together→Groq→Ollama→Gemini→OpenAI) quando disponível;
        cai de volta para o runtime legado caso contrário.

        Retorna: (resposta_final, lista_de_tools_usadas, sucesso)
        """
        # ── Escolher backend de LLM ───────────────────────────────────────
        if _LUNA_ROUTER_AVAILABLE:
            luna_router: LunaLLMRouter = _get_luna_router()
            # Verificar se o provider ativo suporta tool calling
            status = luna_router.status()
            active_provider = status.get("active_provider", "")
            supports_tools = active_provider in ("together", "groq", "openai")

            if not supports_tools:
                # Ollama ou Gemini sem tool calling — usar chat simples
                response = luna_router.chat(messages, temperature=0.2, max_tokens=4096)
                return response, [], True

            # Preparar wrapper para chat_with_tools
            def _llm_call(msgs, tools_schema):
                obj = luna_router.chat_with_tools(msgs, tools=tools_schema, temperature=0.2, max_tokens=4096)
                return obj  # retorna objeto com .choices[0]
        else:
            # Fallback legado
            legacy = self.c.runtime.model_router
            provider = legacy.config.primary_model
            if provider not in ("openai", "grok"):
                response = legacy.call_model(messages=messages, temperature=0.2, max_tokens=4096)
                return response, [], True
            legacy_client = legacy.get_client(provider)
            legacy_model_id = legacy._get_default_model_id(provider)

            def _llm_call(msgs, tools_schema):
                return legacy_client.chat.completions.create(
                    model=legacy_model_id,
                    messages=msgs,
                    tools=tools_schema,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=4096,
                )

        # Combinar todas as ferramentas disponíveis
        tools = (
            FilesystemTool.get_tool_definitions()
            + self._get_meta_tool_definitions()
            + self._get_extra_tool_definitions()
        )

        tools_used: list[str] = []
        tool_call_count = 0
        scan_done = False          # rastrear se scan_project foi chamado
        read_many_done = False     # rastrear se read_many foi chamado após scan
        # Dedup: evitar repetir exatamente o mesmo (tool, args_key) na mesma sessão
        _recent_calls: set[str] = set()

        for iteration in range(max_iters):
            resp = _llm_call(messages, tools)
            choice = resp.choices[0]

            # Resposta final (sem tool calls)
            if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
                final = choice.message.content or ""

                # Guardrail: detectar intenção de análise profunda pelo TEXTO da mensagem
                # (não só pelo task_type, que pode ser classificado errado)
                # IMPORTANTE: messages pode conter dicts OU objetos ChatCompletionMessage (Pydantic)
                # — usar helper _msg_get() para acessar atributos de forma segura
                def _msg_get(m, key: str):
                    """Lê campo de message seja dict ou objeto OpenAI Pydantic."""
                    if isinstance(m, dict):
                        return m.get(key)
                    return getattr(m, key, None)

                _orig_msg = ""
                for _m in reversed(messages):
                    role = _msg_get(_m, "role")
                    content = _msg_get(_m, "content")
                    if role == "user" and content and not str(content).startswith("[GUARDRAIL"):
                        _orig_msg = content
                        break

                _security_keywords = {"vulnerabilidade", "segurança", "seguranca", "análise", "analise",
                                       "audit", "exploit", "bug", "corrija", "verifique", "scan", "review",
                                       "recomendações", "recomendacoes", "recomend"}
                _msg_has_security = any(kw in _orig_msg.lower() for kw in _security_keywords)

                needs_deep = (
                    classification.task_type in ("code_analysis", "security_audit", "refactoring", "bug_fix")
                    or _msg_has_security
                )
                if scan_done and not read_many_done and needs_deep and iteration < max_iters - 3:
                    messages.append({"role": "assistant", "content": final})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[GUARDRAIL ESTRATÉGICO] scan_project foi executado mas read_many NÃO foi chamado. "
                            "Para esta análise ser baseada em código real, você DEVE usar read_many "
                            "para ler os arquivos mais relevantes que apareceram no scan. "
                            "Chame read_many agora com os arquivos de código principal, depois "
                            "chame learn_lesson e então dê a resposta final completa."
                        ),
                    })
                    read_many_done = True  # evitar loop infinito
                    continue

                # Guardrail 2: detectar resposta hollow (vazia de evidências)
                # Se Luna usou ferramentas mas a resposta é vaga/curta, forçar re-resposta
                _hollow_phrases = [
                    "análise concluída", "analise concluida", "tarefa executada",
                    "tarefa concluída", "tarefa concluida", "feito com sucesso",
                    "executado com sucesso", "concluído com sucesso", "concluido com sucesso",
                    "identifiquei as principais", "estou pronta para ajudar",
                    "estou à disposição", "fico à disposição", "se precisar de mais",
                    "posso ajudar com", "qualquer dúvida", "estou disponível",
                ]
                _final_lower = final.lower()
                _has_hollow_phrase = any(ph in _final_lower for ph in _hollow_phrases)
                _is_trivially_short = len(final.strip()) < 100
                _is_hollow = (
                    tool_call_count >= 2
                    and iteration < max_iters - 2
                    and (_has_hollow_phrase or _is_trivially_short)
                )
                if _is_hollow:
                    messages.append({"role": "assistant", "content": final})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[GUARDRAIL DE CONTEÚDO] Sua resposta não apresentou os achados reais. "
                            f"Você executou {tool_call_count} operações mas a resposta está vazia de evidências. "
                            "REGRA 11 VIOLADA: a resposta final DEVE conter:\n"
                            "• Estrutura real do projeto (arquivos encontrados com nomes reais)\n"
                            "• Trechos de código que você leu (cite arquivo + linha)\n"
                            "• Problemas ou funcionalidades identificadas com evidências concretas\n"
                            "• Análise baseada no que está no código, não em suposições\n\n"
                            "Reescreva sua resposta agora apresentando TUDO que você encontrou/leu/analisou."
                        ),
                    })
                    continue

                success = not final.startswith("[Erro")
                return final, tools_used, success

            # Adicionar resposta do assistente ao histórico
            messages.append(choice.message)

            # Executar tool calls
            for tc in choice.message.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                # Converter paths Windows → WSL
                for k in ("path", "cwd"):
                    if k in args and isinstance(args[k], str):
                        args[k] = self._win_to_wsl(args[k])
                if "paths" in args and isinstance(args.get("paths"), list):
                    args["paths"] = [self._win_to_wsl(p) for p in args["paths"]]

                # Dedup: ignorar chamada idêntica já executada neste loop
                _dedup_key = f"{name}::{json.dumps(args, sort_keys=True, default=str)[:200]}"
                if _dedup_key in _recent_calls:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({
                            "skipped": True,
                            "reason": "Chamada idêntica já executada nesta sessão. Use argumentos diferentes ou prossiga com os resultados anteriores.",
                        }),
                    })
                    continue
                _recent_calls.add(_dedup_key)

                tool_call_count += 1
                tools_used.append(name)
                if name == "scan_project":
                    scan_done = True
                if name in ("read_many", "read_file", "read_file_chunked"):
                    read_many_done = True
                self.c.tool_call(tool_call_count, name, self._summarize_args(args))

                result = self._dispatch(name, args, classification)

                result_str = json.dumps(result, ensure_ascii=False, default=str)
                # Truncar resultado muito grande, preservando início e fim
                if len(result_str) > 50000:
                    half = 24000
                    result_str = (
                        result_str[:half]
                        + "\n...[CONTEÚDO TRUNCADO — use read_file_chunked para partes específicas]...\n"
                        + result_str[-half:]
                    )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

        return (
            "Limite de iterações atingido. Reformule o pedido ou quebre em etapas menores.",
            tools_used,
            False,
        )

    # ── Hunter-V2 Elite Commands ──────────────────────────────────────────

    def _cmd_hunt(self, arg: str) -> None:
        """Orquestrador completo: Triage→Deep Audit→PoC→Relatório Immunefi."""
        if not _HUNTER_AVAILABLE:
            self.c.err("Hunter-V2 não disponível — verifique app/hunter/hunter_engine.py")
            return
        if not arg:
            self.c.err(
                "Uso:\n"
                "  /hunt <path>           — audita projeto local\n"
                "  /hunt <tx_signature>   — analisa transação on-chain\n"
                "  /hunt --live           — monitora Mainnet em tempo real\n"
                "  /hunt --deep <path>    — força deep audit sem confirmar\n"
            )
            return

        import asyncio as _asyncio

        # Parsear flags
        force_deep = "--deep" in arg
        live_mode  = "--live" in arg
        arg_clean  = arg.replace("--deep", "").replace("--live", "").strip()

        # Detectar modo pelo target
        if live_mode:
            mode = HuntMode.LIVE_STREAM
            target = arg_clean or ""
            # Extrair --program flag
            program_ids = []
            if "--program" in arg:
                parts = arg.split("--program")
                if len(parts) > 1:
                    prog = parts[1].strip().split()[0]
                    program_ids.append(prog)
        elif arg_clean and len(arg_clean) >= 80 and " " not in arg_clean:
            # Parece uma assinatura de transação (base58, 87-88 chars)
            mode = HuntMode.TX_SIGNATURE
            target = arg_clean
            program_ids = []
        else:
            mode = HuntMode.LOCAL_PATH
            target = self._win_to_wsl(arg_clean) if arg_clean else ""
            program_ids = []

        if mode == HuntMode.LOCAL_PATH and not target:
            self.c.err("Especifique um caminho de projeto: /hunt /mnt/d/Dev/meu-protocolo")
            return

        # Detectar protocol name pelo path
        protocol_name = Path(target).name if target and mode == HuntMode.LOCAL_PATH else "Unknown"

        # Callback de confirmação para deep audit
        def confirm_deep(msg: str, grains: int) -> bool:
            self.c.p(f"\n[bold yellow]⚠️  Deep Audit Request[/bold yellow]")
            self.c.p(f"  {msg}")
            self.c.p(f"  [dim]Custo estimado: {grains:,} Grains[/dim]")
            answer = self.c.console.input("  Aprovar? [s/N]: ").strip().lower()
            return answer in ("s", "sim", "y", "yes")

        cfg = HuntConfig(
            target=target,
            mode=mode,
            protocol_name=protocol_name,
            program_id=program_ids[0] if program_ids else None,
            deep_audit=force_deep,
            auto_approve_grains=force_deep,
            output_dir=(str(Path(target) / "luna_hunter_output")
                        if mode == HuntMode.LOCAL_PATH and target else "luna_hunter_output"),
            network="mainnet",
            stream_program_ids=program_ids,
        )

        mode_icons = {
            HuntMode.LOCAL_PATH:   "📂",
            HuntMode.TX_SIGNATURE: "🔍",
            HuntMode.LIVE_STREAM:  "📡",
        }
        self.c.p(f"\n[bold cyan]{mode_icons[mode]} LUNA HUNTER-V2 ELITE[/bold cyan]")
        self.c.p(f"[dim]Modo: {mode.value}  |  Alvo: {target or 'Mainnet'}[/dim]")
        if mode == HuntMode.LOCAL_PATH:
            self.c.p("[dim]Fases: Audit Estático → Triage LLM → Deep Audit → PoC → Relatório[/dim]")

        engine = get_hunter_engine(confirm_deep)

        try:
            loop = _asyncio.new_event_loop()
            result = loop.run_until_complete(engine.hunt(cfg))
            loop.close()
        except Exception as e:
            self.c.err(f"Erro no hunt: {e}")
            return

        # Exibir resultado
        elapsed = f"{result.duration_s:.1f}s"
        if result.error:
            self.c.err(f"Hunt encerrado com erro ({elapsed}): {result.error}")
        else:
            self.c.p(f"\n[bold green]✓ Hunt concluído em {elapsed}[/bold green]")

        if result.triage_summary:
            self.c.p(f"\n[bold cyan]📊 Triage:[/bold cyan]")
            self.c.console.print(
                Panel(result.triage_summary[:3000], border_style="cyan", padding=(0, 2))
            )

        if result.deep_summary:
            self.c.p(f"\n[bold magenta]🧠 Deep Audit:[/bold magenta]")
            self.c.console.print(
                Panel(result.deep_summary[:4000], border_style="magenta", padding=(0, 2))
            )

        # Sumário final
        if result.findings_count > 0:
            sev_color = "red" if result.critical_count > 0 else ("yellow" if result.high_count > 0 else "green")
            self.c.p(
                f"\n[bold {sev_color}]"
                f"🔒 Findings: {result.findings_count} total  |  "
                f"Critical: {result.critical_count}  |  High: {result.high_count}"
                f"[/bold {sev_color}]"
            )

        if result.poc_files:
            self.c.p(f"\n[cyan]PoCs gerados:[/cyan]")
            for f in result.poc_files:
                self.c.p(f"  [dim]→ {f}[/dim]")

        if result.report_files:
            self.c.p(f"\n[green]Relatórios Immunefi:[/green]")
            for f in result.report_files:
                self.c.p(f"  [dim]→ {f}[/dim]")

        if result.grains_spent:
            self.c.p(f"\n[dim]💎 Grains gastos neste hunt: {result.grains_spent:,}[/dim]")

    def _cmd_generate_poc(self, arg: str) -> None:
        """Gera PoC para findings existentes de uma auditoria."""
        if not _HUNTER_AVAILABLE:
            self.c.err("Hunter-V2 não disponível")
            return
        if not arg:
            self.c.err("Uso: /generate-poc <path_do_projeto>")
            return

        path = self._win_to_wsl(arg)
        report_path = Path(path) / "LUNA_SECURITY_REPORT.md"
        output_dir = str(Path(path) / "luna_hunter_output" / "pocs")

        self.c.thinking("Gerando PoCs a partir dos findings existentes...")

        # Tentar carregar findings do AuditEngine
        try:
            from app.core.audit_engine import AuditEngine
            from app.hunter.poc_generator import PoCGenerator

            engine = AuditEngine()
            audit_report = engine.audit(path)
            gen = PoCGenerator()
            all_files = []

            critical_high = [
                f for f in audit_report.findings
                if f.severity.value.lower() in ("critical", "high")
            ]

            if not critical_high:
                self.c.p("[yellow]Nenhum finding Critical/High encontrado. Usando todos.[/yellow]")
                critical_high = audit_report.findings[:10]

            for finding in critical_high[:5]:
                self.c.p(f"  [dim]Gerando PoC para: [{finding.severity.value}] {finding.title}[/dim]")
                result = gen.generate_from_finding(
                    program_id=finding.file or "PROGRAM_ID_HERE",
                    finding_title=finding.title,
                    finding_description=finding.description,
                    file_path=finding.file,
                    line=finding.line,
                )
                files = result.save(output_dir)
                all_files.extend(files)

            if all_files:
                self.c.ok(f"PoCs gerados em: {output_dir}")
                for f in all_files:
                    self.c.p(f"  [dim]→ {f}[/dim]")
            else:
                self.c.p("[yellow]Nenhum PoC gerado.[/yellow]")

        except Exception as e:
            self.c.err(f"Erro ao gerar PoCs: {e}")

    def _cmd_report_format(self, arg: str) -> None:
        """Formata relatório de auditoria no padrão Immunefi."""
        if not _HUNTER_AVAILABLE:
            self.c.err("Hunter-V2 não disponível")
            return
        if not arg:
            self.c.err("Uso: /report-format <path_do_projeto>")
            return

        path = self._win_to_wsl(arg)
        output_dir = str(Path(path) / "luna_hunter_output")
        protocol_name = Path(path).name

        self.c.thinking(f"Formatando relatório Immunefi para {protocol_name}...")

        try:
            from app.core.audit_engine import AuditEngine
            from app.hunter.report_formatter import ReportFormatter

            engine = AuditEngine()
            audit_report = engine.audit(path)

            formatter = ReportFormatter(protocol_name=protocol_name)
            immunefi_report = formatter.from_audit_findings(
                findings=audit_report.findings,
                protocol_name=protocol_name,
                program_id=None,
                tvl_usd=None,
            )

            saved = formatter.save(immunefi_report, output_dir)

            self.c.ok(f"Relatório Immunefi gerado:")
            for f in saved:
                self.c.p(f"  [dim]→ {f}[/dim]")

            # Preview do cabeçalho
            total = len(immunefi_report.findings)
            critical = sum(1 for f in immunefi_report.findings
                           if f.severity.value == "Critical")
            high = sum(1 for f in immunefi_report.findings
                       if f.severity.value == "High")
            self.c.p(f"\n[bold]Findings: {total} total  |  Critical: {critical}  |  High: {high}[/bold]")

        except Exception as e:
            self.c.err(f"Erro ao gerar relatório: {e}")

    def _cmd_grains(self, arg: str) -> None:
        """Gerencia saldo de Luna Grains."""
        if not _HUNTER_AVAILABLE:
            self.c.err("Hunter-V2 não disponível")
            return

        grains = get_grains_manager()

        if arg.lower().startswith("topup"):
            parts = arg.split()
            if len(parts) < 2 or not parts[1].isdigit():
                self.c.err("Uso: /grains topup <quantidade>  ex: /grains topup 5000")
                return
            amount = int(parts[1])
            grains.top_up(amount, reason="manual topup via CLI")
            self.c.ok(f"+{amount:,} Grains adicionados. Novo saldo: {grains.balance:,}g")
            return

        # Status padrão
        self.c.p(f"\n{grains.render_status()}")

        summary = grains.get_summary()
        if summary["last_5_transactions"]:
            self.c.p("\n[dim]Últimas transações:[/dim]")
            for tx in summary["last_5_transactions"]:
                self.c.p(
                    f"  [dim]{tx['op']:20s} {tx['model']:25s} "
                    f"tokens={tx['tokens']:15s} -{tx['grains']}g  (${tx['usd']:.5f})[/dim]"
                )

    # ── Comandos Especializados ───────────────────────────────────────────

    def _cmd_audit(self, arg: str) -> None:
        """Auditoria de segurança direta via AuditEngine (sem LLM)."""
        if not _AUDIT_AVAILABLE:
            self.c.err("AuditEngine não disponível — verifique app/core/audit_engine.py")
            return
        if not arg:
            self.c.err("Uso: /audit <caminho>  ex: /audit /mnt/d/Dev/meu-protocolo")
            return

        path = self._win_to_wsl(arg)
        from pathlib import Path as _Path
        if not _Path(path).exists():
            self.c.err(f"Caminho não encontrado: {path}")
            return

        self.c.thinking(f"Auditando {path} ...")
        try:
            engine = AuditEngine()
            report = engine.audit(path)

            # Cabeçalho no terminal
            score = report.score()
            score_color = "red" if score < 50 else ("yellow" if score < 80 else "green")
            self.c.p(f"\n[bold {score_color}]🔒 LUNA SECURITY AUDIT — Score: {score}/100[/bold {score_color}]")
            self.c.p(f"[dim]Stack: {report.stack} | Arquivos: {report.files_scanned} | "
                     f"Findings: {len(report.findings)}[/dim]\n")

            # Findings por severidade
            by_sev = report.by_severity()
            sev_colors = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "cyan", "info": "dim"}
            sev_icons  = {"critical": "🚨", "high": "❌", "medium": "⚠️", "low": "ℹ️", "info": "💡"}

            for sev in ("critical", "high", "medium", "low", "info"):
                findings = by_sev.get(sev, [])
                if not findings:
                    continue
                self.c.p(f"[{sev_colors[sev]}]{sev_icons[sev]}  {sev.upper()} ({len(findings)})[/{sev_colors[sev]}]")
                for f in findings:
                    loc = f"{f.file}:{f.line}" if f.line else f.file
                    self.c.p(f"  [{f.rule_id}] {f.title}")
                    self.c.p(f"  [dim]  {loc}[/dim]")
                    if f.snippet:
                        snippet_short = f.snippet.strip()[:120].replace("\n", " ")
                        self.c.p(f"  [dim cyan]  → {snippet_short}[/dim cyan]")
                    self.c.p(f"  [dim]  💡 {f.recommendation}[/dim]")
                    self.c.p()

            if not report.findings:
                self.c.ok("Nenhuma vulnerabilidade encontrada nos padrões conhecidos.")

            # Salvar relatório markdown no projeto
            try:
                md_path = _Path(path) / "LUNA_SECURITY_REPORT.md"
                md_path.write_text(report.render_markdown(), encoding="utf-8")
                self.c.ok(f"Relatório salvo em: {md_path}")
            except Exception as e:
                self.c.c.print(f"[dim]Não foi possível salvar relatório: {e}[/dim]")

        except Exception as e:
            self.c.err(f"Erro na auditoria: {e}")
            logger.exception("Erro em _cmd_audit")

    def _cmd_router(self, arg: str) -> None:
        """Mostra status dos provedores LLM ou reseta falhas."""
        if not _LUNA_ROUTER_AVAILABLE:
            self.c.err("LunaLLMRouter não disponível — verifique app/llm_router.py e dependências")
            return

        router = _get_luna_router()

        if arg.strip().lower() == "reset":
            provider_arg = None  # reset todos
            router.reset(provider_arg)
            self.c.ok("Estado de todos os provedores resetado.")
            return

        status = router.status()
        t = Table(title="🔀 Luna LLM Router — Status dos Provedores")
        t.add_column("Provedor")
        t.add_column("Modelo")
        t.add_column("Status")
        t.add_column("Falhas", justify="right")
        t.add_column("Contexto", justify="right")

        for p_info in status.get("providers", []):
            name = p_info["name"]
            is_active = (name == status.get("active_provider"))
            state_str = p_info.get("state", "unknown")

            if is_active:
                state_display = "[bold green]◉ ATIVO[/bold green]"
            elif state_str == "ok":
                state_display = "[green]○ pronto[/green]"
            elif state_str == "cooldown":
                state_display = "[yellow]⏳ cooldown[/yellow]"
            else:
                state_display = "[red]✗ inativo[/red]"

            t.add_row(
                f"[bold]{name}[/bold]" if is_active else name,
                p_info.get("model", "-"),
                state_display,
                str(p_info.get("failures", 0)),
                f"{p_info.get('context_limit', 0):,}",
            )

        self.c.console.print(Panel(t))
        ctx_limit = status.get("context_limit", 0)
        self.c.p(f"[dim]Contexto disponível: {ctx_limit:,} tokens  |  Use /router reset para limpar falhas[/dim]")

    # ── Dispatch de Ferramentas ───────────────────────────────────────────

    def _dispatch(self, name: str, args: dict, classification: TaskClassification | None = None) -> dict:
        fs = self.c.fs
        strategy = self.c.strategy
        try:
            match name:
                # ── Filesystem ──────────────────────────────────────────
                case "list_dir":
                    return fs.list_dir(args["path"], args.get("show_hidden", False))
                case "read_file":
                    return fs.read_file(args["path"], args.get("max_chars", 8000))
                case "read_file_chunked":
                    return fs.read_file_chunked(
                        args["path"],
                        args.get("chunk_size", 6000),
                        args.get("chunk_index", 0),
                    )
                case "write_file":
                    return fs.write_file(args["path"], args["content"])
                case "patch_file":
                    return fs.patch_file(args["path"], args["old"], args["new"])
                case "search_files":
                    return fs.search_files(args["path"], args["pattern"])
                case "grep_file":
                    return fs.grep_file(args["path"], args["query"])
                case "run_command":
                    return fs.run_command(
                        args["command"],
                        args.get("cwd"),
                        args.get("timeout", 30),
                    )
                case "create_dir":
                    return fs.create_dir(args["path"])
                case "scan_project":
                    # Para segurança e análise, aumentar max_files automaticamente
                    task_type = classification.task_type if classification else "general"
                    default_max = 50 if task_type in (
                        "security_audit", "code_analysis"
                    ) else 30
                    return fs.scan_project(args["path"], args.get("max_files", default_max))
                case "read_many":
                    return fs.read_many(args["paths"])
                case "web_search":
                    return fs.web_search(args["query"], args.get("max_results", 5))
                case "allow_dir":
                    result = fs.allow_dir(args["path"])
                    if result.get("ok"):
                        self._persist_allowed_dirs()
                    return result

                # ── Memória de Contexto ─────────────────────────────────
                case "save_context":
                    key = args.get("key", "geral")
                    value = args.get("value", "")
                    self.c.save_context(key, value)
                    return {"ok": True, "key": key, "chars_saved": len(value)}
                case "get_context":
                    key = args.get("key", "geral")
                    value = self.c.get_context(key)
                    if value:
                        return {"key": key, "value": value, "found": True}
                    # Tentar encontrar chave parcial
                    partial = [
                        (k, v) for k, v in self.c._project_context.items()
                        if key.lower() in k.lower()
                    ]
                    if partial:
                        return {"key": key, "matches": [k for k, _ in partial], "value": partial[0][1], "found": True}
                    return {"key": key, "value": None, "found": False, "available_keys": list(self.c._project_context.keys())}

                # ── Aprendizado Estratégico ─────────────────────────────
                case "learn_lesson":
                    # Normalizar tools_used — o modelo envia string, lista ou até inteiro
                    raw_tools = args.get("tools_used", [])
                    if isinstance(raw_tools, str):
                        # "scan_project, read_many, grep_file" → lista
                        tools_list = [t.strip() for t in raw_tools.replace(";", ",").split(",") if t.strip()]
                    elif isinstance(raw_tools, list):
                        # Filtrar: manter só strings, descartar inteiros/None
                        tools_list = [str(t).strip() for t in raw_tools if isinstance(t, str) and t.strip()]
                        # Se só vieram inteiros (ex: [3]), reconstruir da lista real de tools usadas
                        if not tools_list:
                            tools_list = tools_used[-10:] if tools_used else []
                    elif isinstance(raw_tools, int):
                        # modelo mandou o número total em vez da lista — usar tools reais
                        tools_list = tools_used[-raw_tools:] if tools_used else []
                    else:
                        tools_list = tools_used[-5:] if tools_used else []
                    strategy.save_lesson(
                        task_type=args.get("task_type", "general"),
                        task_summary=args.get("task_summary", "")[:200],
                        what_worked=args.get("what_worked", "")[:500],
                        what_failed=args.get("what_failed", "")[:300],
                        tools_used=tools_list,
                        outcome=args.get("outcome", "success"),
                        notes=args.get("notes", "")[:300],
                    )
                    return {"ok": True, "lesson_saved": True, "task_type": args.get("task_type"), "tools_count": len(tools_list)}
                case "get_lessons":
                    task_type = args.get("task_type")
                    lessons = strategy.load_lessons(task_type, limit=args.get("limit", 5))
                    return {
                        "lessons": [
                            {
                                "task_type": l.task_type,
                                "summary": l.task_summary,
                                "what_worked": l.what_worked,
                                "what_failed": l.what_failed,
                                "outcome": l.outcome,
                                "tools_used": l.tools_used,
                                "timestamp": l.timestamp,
                            }
                            for l in lessons
                        ],
                        "count": len(lessons),
                    }

                case _:
                    return {"error": f"Ferramenta desconhecida: {name}"}

        except Exception as e:
            logger.error(f"Erro ao executar {name}: {e}", exc_info=True)
            return {"error": str(e), "tool": name}

    # ── Definições de Ferramentas Meta (Aprendizado) ──────────────────────

    @staticmethod
    def _get_meta_tool_definitions() -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "learn_lesson",
                    "description": (
                        "Salva uma lição aprendida após completar uma tarefa. "
                        "SEMPRE chame isso ao final de tarefas complexas — especialmente quando "
                        "algo funcionou de forma não-óbvia ou quando algo falhou. "
                        "Essas lições são carregadas em tarefas futuras similares, "
                        "tornando você progressivamente mais eficiente."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_type": {
                                "type": "string",
                                "enum": [
                                    "code_analysis", "bug_fix", "code_generation",
                                    "security_audit", "project_setup", "refactoring",
                                    "research", "shell_task", "general",
                                ],
                                "description": "Tipo da tarefa executada",
                            },
                            "task_summary": {
                                "type": "string",
                                "description": "Resumo da tarefa em 1-2 frases",
                            },
                            "what_worked": {
                                "type": "string",
                                "description": (
                                    "O que funcionou bem — sequência de ferramentas, abordagem, "
                                    "insights específicos. Seja específico."
                                ),
                            },
                            "what_failed": {
                                "type": "string",
                                "description": "O que falhou ou foi ineficiente. Pode ser vazio se tudo funcionou.",
                            },
                            "tools_used": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Lista de ferramentas usadas em ordem",
                            },
                            "outcome": {
                                "type": "string",
                                "enum": ["success", "partial", "failed"],
                                "description": "Resultado: sucesso total, parcial, ou falhou",
                            },
                            "notes": {
                                "type": "string",
                                "description": "Notas adicionais, padrões descobertos, atenções para o futuro",
                            },
                        },
                        "required": ["task_type", "task_summary", "what_worked", "outcome"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_lessons",
                    "description": (
                        "Recupera lições aprendidas de tarefas anteriores similares. "
                        "Use no INÍCIO de tarefas complexas para aproveitar experiências passadas."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_type": {
                                "type": "string",
                                "description": "Tipo de tarefa para filtrar (opcional — omita para todas)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Número máximo de lições (padrão: 5)",
                                "default": 5,
                            },
                        },
                        "required": [],
                    },
                },
            },
        ]

    @staticmethod
    def _get_extra_tool_definitions() -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "save_context",
                    "description": (
                        "Salva um fato ou resumo sobre um projeto na memória da sessão. "
                        "USE após scan_project para guardar: stack, arquivos principais, "
                        "estado atual, bugs encontrados. "
                        "Isso evita reler o projeto toda vez que o usuário faz uma nova pergunta."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "Identificador (ex: 'bags-api', 'vault-program', 'task-atual')",
                            },
                            "value": {
                                "type": "string",
                                "description": "Conteúdo a salvar — pode ser markdown",
                            },
                        },
                        "required": ["key", "value"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_context",
                    "description": "Recupera contexto salvo sobre um projeto ou tarefa.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "Chave do contexto (busca parcial também funciona)",
                            },
                        },
                        "required": ["key"],
                    },
                },
            },
        ]

    # ── Utilitários ───────────────────────────────────────────────────────

    @staticmethod
    def _win_to_wsl(path: str) -> str:
        """Converte C:\\Dev → /mnt/c/Dev."""
        p = path.strip().strip('"').strip("'")
        if len(p) >= 2 and p[1] == ":" and (len(p) == 2 or p[2] in ("/", "\\")):
            drive = p[0].lower()
            rest = p[2:].replace("\\", "/")
            return f"/mnt/{drive}{rest}"
        return p.replace("\\", "/")

    @staticmethod
    def _summarize_args(args: dict) -> str:
        parts = []
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 60:
                parts.append(f'{k}="{v[:57]}..."')
            elif isinstance(v, list):
                parts.append(f"{k}=[{len(v)}]")
            else:
                parts.append(f'{k}="{v}"')
        return ", ".join(parts)

    def _persist_allowed_dirs(self) -> None:
        env_path = Path(__file__).parents[1] / ".env"
        if not env_path.exists():
            return
        try:
            lines = env_path.read_text().splitlines()
            new_val = ",".join(str(d) for d in self.c.fs.allowed_dirs)
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("LUNA_ALLOWED_DIRS="):
                    if not found:
                        new_lines.append(f"LUNA_ALLOWED_DIRS={new_val}")
                        found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"LUNA_ALLOWED_DIRS={new_val}")
            env_path.write_text("\n".join(new_lines) + "\n")
        except Exception as e:
            logger.warning(f"Erro ao persistir LUNA_ALLOWED_DIRS: {e}")

    def _print_ls(self, result: dict) -> None:
        if "error" in result:
            self.c.err(result["error"])
            return
        t = Table(title=result["path"], show_header=True, header_style="bold")
        t.add_column("", width=3)
        t.add_column("Nome")
        t.add_column("Tamanho", justify="right")
        for e in result["entries"]:
            icon = "📁" if e["type"] == "dir" else "📄"
            size = f"{e['size']:,}" if e.get("size") is not None else "-"
            t.add_row(icon, e["name"], size)
        self.c.console.print(t)

    def _print_run(self, result: dict) -> None:
        if "error" in result:
            self.c.err(result["error"])
            return
        color = "green" if result.get("ok") else "red"
        self.c.p(f"[{color}]$ {result.get('command', '')}  (exit {result.get('returncode', '?')})[/{color}]")
        if result.get("stdout"):
            self.c.p(result["stdout"])
        if result.get("stderr"):
            self.c.p(f"[dim red]{result['stderr']}[/dim red]")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logging.getLogger("luna").setLevel(logging.INFO)
    Path("logs").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    LunaCLI().run()


if __name__ == "__main__":
    main()
