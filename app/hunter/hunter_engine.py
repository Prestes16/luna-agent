"""
Luna Hunter Engine
===================
Orchestrador principal do módulo Hunter-V2 Elite.

Fluxo de auditoria:
  1. TRIAGE (Tier-1, Groq Llama-3-8B)
     - AuditToolkit rápido (Anchor-Linter + cargo-audit)
     - LLM analisa findings + código — custo ≈ zero
     - Decide: "continuar para deep audit?" ou "encerrar"

  2. DEEP AUDIT (Tier-2, Together AI 405B)
     - Solicita confirmação do usuário (custo estimado)
     - AuditToolkit completo (+ Soteria + SPT)
     - LLM com contexto 128k — lê todo o projeto
     - Gera análise técnica detalhada

  3. PoC GENERATION
     - Para cada finding High/Critical
     - Gera PoC Rust + TypeScript

  4. REPORT
     - Formata relatório no padrão Immunefi
     - Salva em arquivos .md e .json

Modos:
  local_path  — audita diretório de projeto Anchor/Solana
  tx_signature — analisa transação on-chain via Helius RPC
  live_stream  — monitora Mainnet em tempo real via LaserStream
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("luna.hunter")


# ─── Configuração do Hunt ─────────────────────────────────────────────────────

class HuntMode(str, Enum):
    LOCAL_PATH   = "local_path"
    TX_SIGNATURE = "tx_signature"
    LIVE_STREAM  = "live_stream"


@dataclass
class HuntConfig:
    target:              str                      # path ou signature ou program_id
    mode:                HuntMode = HuntMode.LOCAL_PATH
    protocol_name:       str = "Unknown Protocol"
    program_id:          Optional[str] = None
    tvl_usd:             Optional[float] = None
    run_fuzzer:          bool = False
    fuzz_duration_s:     int = 60
    deep_audit:          bool = False             # skip Tier-2 confirmation
    auto_approve_grains: bool = False             # auto-debitar sem confirmar
    output_dir:          Optional[str] = None
    network:             str = "mainnet"          # mainnet | devnet | localnet
    stream_program_ids:  list[str] = field(default_factory=list)
    stream_duration_s:   int = 3600               # 1h padrão para live stream


@dataclass
class HuntResult:
    config:          HuntConfig
    mode:            HuntMode
    started_at:      float
    finished_at:     float = 0.0
    triage_summary:  str = ""
    deep_summary:    str = ""
    findings_count:  int = 0
    critical_count:  int = 0
    high_count:      int = 0
    poc_files:       list[str] = field(default_factory=list)
    report_files:    list[str] = field(default_factory=list)
    grains_spent:    int = 0
    error:           Optional[str] = None
    raw_toolkit:     Optional[object] = None  # ToolkitReport
    raw_audit:       Optional[object] = None  # AuditReport (static)
    immunefi_report: Optional[object] = None  # ImmunefiBountyReport

    @property
    def duration_s(self) -> float:
        return (self.finished_at or time.time()) - self.started_at


# ─── Hunter Engine ────────────────────────────────────────────────────────────

class HunterEngine:
    """
    Motor principal de auditoria Hunter-V2.

    Uso:
        engine = HunterEngine()
        result = await engine.hunt(HuntConfig(
            target="/mnt/d/Dev/bags-shield",
            protocol_name="bags-shield",
            tvl_usd=1_000_000,
        ))
        print(result.triage_summary)
    """

    def __init__(
        self,
        confirm_callback: Optional[Callable[[str, int], bool]] = None,
    ) -> None:
        """
        Args:
            confirm_callback: Função chamada para pedir confirmação ao usuário.
                              Recebe (mensagem, grains_estimados) → bool.
                              Se None, usa auto-approve.
        """
        self._confirm = confirm_callback or (lambda msg, g: True)
        self._grains = None  # lazy import
        self._router = None  # lazy import

    # ── API Pública ────────────────────────────────────────────────────────

    async def hunt(self, cfg: HuntConfig) -> HuntResult:
        """Executa o fluxo completo de auditoria."""
        result = HuntResult(
            config=cfg,
            mode=cfg.mode,
            started_at=time.time(),
        )

        try:
            if cfg.mode == HuntMode.LOCAL_PATH:
                await self._hunt_local(cfg, result)
            elif cfg.mode == HuntMode.TX_SIGNATURE:
                await self._hunt_tx(cfg, result)
            elif cfg.mode == HuntMode.LIVE_STREAM:
                await self._hunt_live(cfg, result)
        except Exception as e:
            logger.error(f"[hunter] Erro no hunt: {e}", exc_info=True)
            result.error = str(e)

        result.finished_at = time.time()
        return result

    async def hunt_sync(self, cfg: HuntConfig) -> HuntResult:
        """Versão síncrona para uso no CLI."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # Já dentro de um loop async — criar tarefa
            return await self.hunt(cfg)
        else:
            return loop.run_until_complete(self.hunt(cfg))

    # ── Hunt: Projeto Local ────────────────────────────────────────────────

    async def _hunt_local(self, cfg: HuntConfig, result: HuntResult) -> None:
        path = Path(cfg.target)
        if not path.exists():
            raise FileNotFoundError(f"Caminho não encontrado: {cfg.target}")

        output_dir = cfg.output_dir or str(path / "luna_hunter_output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # ── FASE 1: Static Audit (AuditEngine) ─────────────────────────
        logger.info(f"[hunter] FASE 1: Static audit em {cfg.target}")
        audit_report = await asyncio.get_event_loop().run_in_executor(
            None, self._run_static_audit, cfg.target
        )
        result.raw_audit = audit_report

        # ── FASE 2: Toolkit rápido (Anchor-Linter + cargo-audit) ───────
        logger.info("[hunter] FASE 2: Toolkit rápido (Tier-1 triage)")
        toolkit_report = await asyncio.get_event_loop().run_in_executor(
            None, self._run_toolkit_fast, cfg.target
        )
        result.raw_toolkit = toolkit_report

        # ── FASE 3: Triage LLM (Groq Llama-3-8B — Tier 0) ─────────────
        logger.info("[hunter] FASE 3: Triage LLM (Groq — custo zero)")
        triage_result = await self._llm_triage(
            project_path=cfg.target,
            audit_findings=audit_report.findings if hasattr(audit_report, "findings") else [],
            toolkit_findings=toolkit_report.all_findings if toolkit_report else [],
            cfg=cfg,
            result=result,
        )
        result.triage_summary = triage_result.get("summary", "")
        should_deep = triage_result.get("should_deep_audit", False)

        # ── FASE 4: Deep Audit (Together AI 405B — Tier 1) ─────────────
        if should_deep and not cfg.deep_audit:
            # Pedir confirmação ao usuário
            grains_est = self._estimate_deep_grains(cfg.target)
            message = (
                f"Triage detectou padrões suspeitos. "
                f"Deep audit com Llama-3.1-405B custará ~{grains_est:,} Grains. "
                f"Aprovar deep audit?"
            )
            approved = cfg.auto_approve_grains or self._confirm(message, grains_est)
            should_deep = approved

        if should_deep or cfg.deep_audit:
            logger.info("[hunter] FASE 4: Deep audit LLM (Together AI 405B — Tier 1)")
            deep_result = await self._llm_deep_audit(
                project_path=cfg.target,
                triage_context=result.triage_summary,
                cfg=cfg,
                result=result,
            )
            result.deep_summary = deep_result.get("summary", "")

        # ── FASE 5: Toolkit completo (opcional — com Soteria/Trident) ───
        if cfg.run_fuzzer:
            logger.info("[hunter] FASE 5: Toolkit completo com fuzzing...")
            toolkit_full = await asyncio.get_event_loop().run_in_executor(
                None, self._run_toolkit_full, cfg.target, cfg.fuzz_duration_s
            )
            # Merge findings
            if toolkit_report and toolkit_full:
                toolkit_report.results.extend(toolkit_full.results)

        # ── FASE 6: Consolidar findings ─────────────────────────────────
        all_findings = []
        if hasattr(audit_report, "findings"):
            all_findings.extend(audit_report.findings)
        if toolkit_report:
            all_findings.extend(toolkit_report.all_findings)

        result.findings_count = len(all_findings)
        result.critical_count = sum(
            1 for f in all_findings
            if (getattr(f, "severity", "") if not isinstance(getattr(f, "severity", ""), str)
                else getattr(f, "severity", "")).lower() in ("critical",)
               or str(getattr(f, "severity", "")).lower() == "critical"
        )
        result.high_count = sum(
            1 for f in all_findings
            if str(getattr(f, "severity", "")).lower() == "high"
        )

        # ── FASE 7: Gerar PoCs para Critical/High ──────────────────────
        critical_high = [
            f for f in all_findings
            if str(getattr(f, "severity", "")).lower() in ("critical", "high")
        ]
        poc_files = await self._generate_pocs(
            findings=critical_high,
            program_id=cfg.program_id,
            output_dir=output_dir,
        )
        result.poc_files = [str(p) for p in poc_files]

        # ── FASE 8: Gerar relatório Immunefi ───────────────────────────
        logger.info("[hunter] FASE 8: Gerando relatório Immunefi")
        poc_map = {}  # rule_id → poc_code string
        report_files = await self._generate_report(
            audit_findings=all_findings,
            cfg=cfg,
            output_dir=output_dir,
            poc_map=poc_map,
        )
        result.report_files = [str(p) for p in report_files]
        logger.info(f"[hunter] Hunt concluído em {result.duration_s:.1f}s")

    # ── Hunt: Transação On-Chain ───────────────────────────────────────────

    async def _hunt_tx(self, cfg: HuntConfig, result: HuntResult) -> None:
        """Analisa transação específica via Helius RPC."""
        from app.hunter.laser_stream_service import TxAnalyzer

        logger.info(f"[hunter] Analisando TX: {cfg.target}")
        analyzer = TxAnalyzer()

        tx_data = await analyzer.analyze(cfg.target)

        if tx_data.get("error"):
            result.error = tx_data["error"]
            return

        # Formatar análise
        sig = tx_data["signature"]
        status = tx_data["status"]
        programs = tx_data.get("program_ids", [])
        logs = tx_data.get("log_messages", [])
        err = tx_data.get("error_type")
        exploitable = tx_data.get("exploitable_candidate", False)

        summary_lines = [
            f"## Análise de Transação: `{sig[:16]}...`",
            f"**Status:** `{status}`",
            f"**Programas:** {', '.join(f'`{p[:8]}...`' for p in programs[:5])}",
        ]
        if err:
            summary_lines.append(f"**Erro:** `{err}`")
            if tx_data.get("error_detail"):
                summary_lines.append(f"**Detalhe:** {tx_data['error_detail']}")

        if tx_data.get("sol_changes"):
            for chg in tx_data["sol_changes"][:5]:
                delta = chg["delta_sol"]
                direction = "recebeu" if delta > 0 else "enviou"
                summary_lines.append(f"**{chg['account'][:8]}...** {direction} {abs(delta):.4f} SOL")

        if exploitable:
            summary_lines.append(
                "\n⚠️ **Esta transação é candidata explorável** — "
                "padrão de erro sugere bug de lógica ou tentativa de ataque frustrada."
            )
            # LLM Triage dos logs
            triage = await self._llm_triage_logs(
                logs=logs,
                error_type=err or "",
                programs=programs,
                result=result,
            )
            summary_lines.append(f"\n### Análise LLM (Triage)\n{triage}")

        summary_lines.append("\n### Logs")
        for log in logs[:20]:
            summary_lines.append(f"```\n{log}\n```")

        result.triage_summary = "\n".join(summary_lines)
        result.findings_count = 1 if exploitable else 0

    # ── Hunt: Live Stream ──────────────────────────────────────────────────

    async def _hunt_live(self, cfg: HuntConfig, result: HuntResult) -> None:
        """Monitora Mainnet em tempo real e alerta sobre candidatos exploráveis."""
        from app.hunter.laser_stream_service import LaserStreamClient

        client = LaserStreamClient(devnet=(cfg.network == "devnet"))
        queue: asyncio.Queue = asyncio.Queue()
        client.add_queue(queue)

        alerts: list[str] = []
        start = time.time()

        logger.info(
            f"[hunter] Iniciando LaserStream — duração: {cfg.stream_duration_s}s  "
            f"programas: {cfg.stream_program_ids or 'todos'}"
        )

        # Iniciar stream em background
        stream_task = asyncio.create_task(
            client.start(
                program_ids=cfg.stream_program_ids or None,
                filter_exploitable_only=True,
            )
        )

        try:
            while time.time() - start < cfg.stream_duration_s:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                    if event.is_exploitable_candidate:
                        alert = (
                            f"🎯 CANDIDATO: `{event.signature[:16]}...` | "
                            f"err={event.error_type} | "
                            f"programs={event.program_ids[:2]}"
                        )
                        alerts.append(alert)
                        logger.info(f"[hunter] {alert}")
                except asyncio.TimeoutError:
                    continue
        finally:
            client.stop()
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass

        stats = client.stats
        result.triage_summary = (
            f"## Live Stream Report\n"
            f"**Duração:** {cfg.stream_duration_s}s\n"
            f"**Total eventos:** {stats['total_events']:,}\n"
            f"**InstructionErrors:** {stats['instruction_errors']:,}\n"
            f"**Candidatos exploráveis:** {stats['exploitable_candidates']:,}\n\n"
            + ("\n".join(alerts[-20:]) if alerts else "_Nenhum candidato detectado._")
        )
        result.findings_count = len(alerts)

    # ── LLM Calls ─────────────────────────────────────────────────────────

    async def _llm_triage(
        self,
        project_path: str,
        audit_findings: list,
        toolkit_findings: list,
        cfg: HuntConfig,
        result: HuntResult,
    ) -> dict:
        """Tier-1: Triage rápido com Groq Llama-3-8B (custo ≈ zero)."""
        router = self._get_tiered_router()
        grains = self._get_grains()

        # Montar contexto de findings para o LLM
        finding_lines = []
        for f in (audit_findings + toolkit_findings)[:30]:  # limitar para caber no contexto
            severity = getattr(f, "severity", "?")
            sev_str = severity.value if hasattr(severity, "value") else str(severity)
            title = getattr(f, "title", str(f))
            file_info = ""
            if hasattr(f, "file") and f.file:
                file_info = f" [{f.file}:{getattr(f, 'line', '?')}]"
            finding_lines.append(f"- [{sev_str.upper()}] {title}{file_info}")

        findings_text = "\n".join(finding_lines) if finding_lines else "Nenhum finding inicial."

        # Ler arquivos principais do projeto (contexto limitado para Tier-1)
        project_context = await asyncio.get_event_loop().run_in_executor(
            None, self._read_project_context_light, project_path
        )

        prompt = f"""Você é um auditor de segurança Solana/Web3 especializado em Immunefi Bug Bounty.

## Projeto: {cfg.protocol_name}
{f"Program ID: {cfg.program_id}" if cfg.program_id else ""}
{f"TVL estimado: ${cfg.tvl_usd:,.0f} USD" if cfg.tvl_usd else ""}

## Findings da Análise Estática:
{findings_text}

## Contexto do Código (arquivos principais):
{project_context[:6000]}

## Tarefa:
1. Avalie rapidamente os findings acima e o contexto do código.
2. Identifique quais findings são REAIS (não falso positivo) e quais são as mais críticas.
3. Determine se há indícios de vulnerabilidades HIGH/CRITICAL que justifiquem uma análise profunda.
4. Responda em JSON com:
{{
  "should_deep_audit": true/false,
  "reason": "por que sim/não",
  "real_findings": ["título dos findings que parecem reais"],
  "suspicious_patterns": ["padrões suspeitos detectados no código"],
  "summary": "resumo técnico em 2-3 parágrafos"
}}"""

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: router.triage(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=1500,
                )
            )
            triage_text, input_tokens, output_tokens = response

            # Debitar Grains
            grains.debit(
                provider="groq", model="llama-3-8b-instant",
                input_tokens=input_tokens, output_tokens=output_tokens,
                operation="audit_triage",
                context=f"hunt:{project_path}",
            )
            result.grains_spent += grains._state.transactions[-1].grains_spent if grains._state.transactions else 0

            # Parsear JSON
            try:
                json_match = __import__("re").search(r"\{.*\}", triage_text, __import__("re").DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    return data
            except Exception:
                pass

            return {
                "should_deep_audit": "critical" in triage_text.lower() or "high" in triage_text.lower(),
                "summary": triage_text,
            }

        except Exception as e:
            logger.warning(f"[hunter] Triage LLM falhou: {e}. Usando heurística local.")
            has_critical = any(
                str(getattr(f, "severity", "")).lower() == "critical"
                for f in audit_findings + toolkit_findings
            )
            return {
                "should_deep_audit": has_critical,
                "summary": f"Triage automática: {len(audit_findings + toolkit_findings)} findings detectados.",
            }

    async def _llm_deep_audit(
        self,
        project_path: str,
        triage_context: str,
        cfg: HuntConfig,
        result: HuntResult,
    ) -> dict:
        """Tier-2: Deep audit com Together AI Llama-3.1-405B (128k context)."""
        router = self._get_tiered_router()
        grains = self._get_grains()

        # Carregar projeto completo (até 120k tokens)
        try:
            from app.core.context_engine import ContextEngine
            ctx_engine = ContextEngine()
            analysis = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ctx_engine.load_project(project_path, budget=100_000)
            )
            project_full_context = ctx_engine.build_prompt_context(
                ctx_engine.load_projects([project_path])
            )
        except Exception as e:
            logger.warning(f"[hunter] ContextEngine falhou: {e} — usando leitura manual")
            project_full_context = await asyncio.get_event_loop().run_in_executor(
                None, self._read_project_context_full, project_path
            )

        prompt = f"""Você é um auditor de segurança de elite especializado em Solana/Anchor para Immunefi Bug Bounty.

## Protocolo: {cfg.protocol_name}
{f"Program ID: {cfg.program_id}" if cfg.program_id else ""}
{f"TVL: ${cfg.tvl_usd:,.0f} USD" if cfg.tvl_usd else ""}

## Contexto da Triage (análise prévia):
{triage_context[:2000]}

## Código Fonte Completo do Projeto:
{project_full_context}

## TAREFA DE AUDITORIA PROFUNDA:
Realize uma auditoria de segurança completa e técnica deste programa Solana.

Para CADA vulnerabilidade encontrada, documente:
- **Título**: nome objetivo da vulnerabilidade
- **Severidade**: Critical / High / Medium / Low (padrão Immunefi)
- **Arquivo e Linha**: localização exata no código
- **Descrição**: explicação técnica detalhada
- **Root Cause**: causa raiz no código
- **Impacto**: consequências concretas (fundos em risco, estado manipulável)
- **Prova**: trecho de código exato que demonstra a vulnerabilidade
- **Fix**: código corrigido (diff ou snippet)

Foque em:
1. Missing signer/owner checks em instruções privilegiadas
2. Arithmetic overflow/underflow sem checked arithmetic
3. PDA bump seed misuse
4. Arbitrary CPI / reentrancy
5. Account confusion (passar account de programa errado)
6. Lógica de negócios incorreta
7. Inicialização insegura de contas

Responda em português. Seja específico — cite arquivo:linha para cada finding."""

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: router.deep_audit(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.15,
                    max_tokens=8000,
                )
            )
            deep_text, input_tokens, output_tokens = response

            # Debitar Grains (markup 1.5x)
            grains.debit(
                provider="together",
                model="meta-llama/Llama-3.1-405B-Instruct-Turbo",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                operation="audit_deep",
                context=f"hunt:{project_path}",
            )
            if grains._state.transactions:
                result.grains_spent += grains._state.transactions[-1].grains_spent

            return {"summary": deep_text}

        except Exception as e:
            logger.error(f"[hunter] Deep audit LLM falhou: {e}")
            return {"summary": f"Deep audit falhou: {e}"}

    async def _llm_triage_logs(
        self,
        logs: list[str],
        error_type: str,
        programs: list[str],
        result: HuntResult,
    ) -> str:
        """Triage de logs de transação on-chain."""
        router = self._get_tiered_router()
        grains = self._get_grains()

        logs_text = "\n".join(logs[:50])
        prompt = f"""Analise estes logs de transação Solana que falhou com erro `{error_type}`.
Programas envolvidos: {programs}

Logs:
{logs_text}

Diga:
1. O que causou a falha?
2. Isso indica um bug de lógica explorável ou erro normal de uso?
3. Qual seria o vetor de ataque se for explorável?

Resposta técnica e concisa (máximo 300 palavras)."""

        try:
            resp, inp, out = router.triage(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=600,
            )
            grains.debit("groq", "llama-3-8b-instant", inp, out, "audit_triage", "tx_analysis")
            return resp
        except Exception as e:
            return f"Análise LLM não disponível: {e}"

    # ── Helpers ────────────────────────────────────────────────────────────

    def _run_static_audit(self, project_path: str):
        try:
            from app.core.audit_engine import AuditEngine
            return AuditEngine().audit(project_path)
        except Exception as e:
            logger.warning(f"[hunter] AuditEngine falhou: {e}")
            return _EmptyAuditReport()

    def _run_toolkit_fast(self, project_path: str):
        try:
            from app.hunter.audit_toolkit import AuditToolkit
            return AuditToolkit().run_fast(project_path)
        except Exception as e:
            logger.warning(f"[hunter] AuditToolkit fast falhou: {e}")
            return None

    def _run_toolkit_full(self, project_path: str, fuzz_duration: int):
        try:
            from app.hunter.audit_toolkit import AuditToolkit
            return AuditToolkit(run_fuzzer=True, fuzz_duration=fuzz_duration).run_all(project_path)
        except Exception as e:
            logger.warning(f"[hunter] AuditToolkit full falhou: {e}")
            return None

    def _read_project_context_light(self, project_path: str, max_chars: int = 8000) -> str:
        """Lê arquivos principais do projeto para contexto de triage."""
        path = Path(project_path)
        priority_patterns = [
            "programs/*/src/lib.rs",
            "programs/*/src/instructions/*.rs",
            "src/lib.rs",
            "programs/**/*.rs",
        ]
        content_parts = []
        total = 0

        for pattern in priority_patterns:
            for file in sorted(path.glob(pattern)):
                if total >= max_chars:
                    break
                try:
                    text = file.read_text("utf-8", errors="ignore")
                    rel = str(file.relative_to(path))
                    snippet = text[:max_chars - total]
                    content_parts.append(f"// === {rel} ===\n{snippet}")
                    total += len(snippet)
                except Exception:
                    pass

        return "\n\n".join(content_parts) if content_parts else "(Sem arquivos Rust encontrados)"

    def _read_project_context_full(self, project_path: str, max_chars: int = 80_000) -> str:
        """Lê todos os arquivos do projeto para deep audit."""
        return self._read_project_context_light(project_path, max_chars)

    def _estimate_deep_grains(self, project_path: str) -> int:
        """Estima custo em Grains para deep audit baseado no tamanho do projeto."""
        total_bytes = sum(
            f.stat().st_size
            for f in Path(project_path).rglob("*.rs")
            if f.is_file()
        )
        # ~4 bytes por token; 405B custa $5/1M tokens; markup 1.5x; 1000 grains/USD
        estimated_tokens = total_bytes // 4 + 4000  # +4k para prompt
        cost_usd = (estimated_tokens / 1_000_000) * 5.0 * 1.5
        return max(50, round(cost_usd * 1000))

    async def _generate_pocs(
        self,
        findings: list,
        program_id: Optional[str],
        output_dir: str,
    ) -> list[Path]:
        """Gera PoCs para findings Critical/High."""
        saved: list[Path] = []
        try:
            from app.hunter.poc_generator import PoCGenerator
            gen = PoCGenerator()

            for finding in findings[:5]:  # limitar a 5 PoCs por hunt
                title = getattr(finding, "title", "")
                desc = getattr(finding, "description", "")
                file_path = getattr(finding, "file", None)
                line = getattr(finding, "line", None)

                poc_result = gen.generate_from_finding(
                    program_id=program_id or "PROGRAM_ID_HERE",
                    finding_title=title,
                    finding_description=desc,
                    file_path=file_path,
                    line=line,
                )
                poc_files = poc_result.save(output_dir)
                saved.extend(poc_files)

        except Exception as e:
            logger.warning(f"[hunter] PoC generation falhou: {e}")

        return saved

    async def _generate_report(
        self,
        audit_findings: list,
        cfg: HuntConfig,
        output_dir: str,
        poc_map: dict,
    ) -> list[Path]:
        """Gera relatório Immunefi."""
        try:
            from app.hunter.report_formatter import ReportFormatter
            formatter = ReportFormatter(protocol_name=cfg.protocol_name)

            immunefi_report = formatter.from_audit_findings(
                findings=audit_findings,
                protocol_name=cfg.protocol_name,
                program_id=cfg.program_id,
                tvl_usd=cfg.tvl_usd,
                poc_map=poc_map,
            )

            return formatter.save(immunefi_report, output_dir)
        except Exception as e:
            logger.warning(f"[hunter] Report generation falhou: {e}")
            return []

    def _get_tiered_router(self):
        if self._router is None:
            try:
                from app.llm_router import get_router, TieredReasoning
                self._router = TieredReasoning(get_router())
            except (ImportError, AttributeError):
                self._router = _FallbackTieredRouter()
        return self._router

    def _get_grains(self):
        if self._grains is None:
            from app.hunter.grains_manager import get_grains_manager
            self._grains = get_grains_manager()
        return self._grains


# ─── Fallbacks ────────────────────────────────────────────────────────────────

class _EmptyAuditReport:
    findings = []
    stack = "unknown"
    files_scanned = 0

    def render_markdown(self) -> str:
        return "Auditoria estática não disponível."

    def score(self) -> int:
        return 100

    def by_severity(self) -> dict:
        return {}


class _FallbackTieredRouter:
    """Fallback quando LunaLLMRouter não está disponível."""

    def triage(self, messages, temperature=0.1, max_tokens=1500):
        raise RuntimeError(
            "LunaLLMRouter não disponível. Configure GROQ_API_KEY no .env"
        )

    def deep_audit(self, messages, temperature=0.15, max_tokens=8000):
        raise RuntimeError(
            "LunaLLMRouter não disponível. Configure TOGETHER_API_KEY no .env"
        )


# ─── Singleton ────────────────────────────────────────────────────────────────

_hunter_engine: HunterEngine | None = None


def get_hunter_engine(
    confirm_callback: Optional[Callable[[str, int], bool]] = None
) -> HunterEngine:
    global _hunter_engine
    if _hunter_engine is None:
        _hunter_engine = HunterEngine(confirm_callback)
    return _hunter_engine
