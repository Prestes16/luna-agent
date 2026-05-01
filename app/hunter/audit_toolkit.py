"""
Luna Audit Toolkit
===================
Orquestrador para ferramentas estáticas e dinâmicas de análise de segurança Solana.

Ferramentas integradas:
  Soteria       — análise estática de programas Solana (Rust)
  Anchor-Linter — linting específico Anchor: signer/owner/constraint checks
  Trident       — fuzzer baseado em propriedades para programas Anchor
  Lanchonete    — gerador de invariantes e testes de propriedade
  cargo-audit   — CVEs em dependências Rust
  Solana-Program-Test — ambiente de simulação para PoC validation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("luna.audit_toolkit")


# ─── Resultados ───────────────────────────────────────────────────────────────

class ToolStatus(str, Enum):
    OK          = "ok"
    FAILED      = "failed"
    NOT_FOUND   = "not_found"
    TIMEOUT     = "timeout"
    SKIPPED     = "skipped"


@dataclass
class ToolFinding:
    tool:        str
    severity:    str          # critical | high | medium | low | info
    rule_id:     str
    title:       str
    description: str
    file:        Optional[str] = None
    line:        Optional[int] = None
    snippet:     Optional[str] = None
    cwe:         Optional[str] = None
    ref:         Optional[str] = None  # link para documentação


@dataclass
class ToolResult:
    tool:           str
    status:         ToolStatus
    duration_s:     float
    findings:       list[ToolFinding] = field(default_factory=list)
    raw_output:     str = ""
    error:          Optional[str] = None
    version:        Optional[str] = None


@dataclass
class ToolkitReport:
    """Resultado agregado de todas as ferramentas."""
    project_path: str
    ran_at:       float
    tools_run:    list[str]
    results:      list[ToolResult]
    total_time_s: float

    @property
    def all_findings(self) -> list[ToolFinding]:
        findings = []
        for r in self.results:
            findings.extend(r.findings)
        # Ordenar: critical → high → medium → low → info
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        findings.sort(key=lambda f: order.get(f.severity, 5))
        return findings

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.all_findings if f.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.all_findings if f.severity == "high")


# ─── Runners individuais ──────────────────────────────────────────────────────

class _ToolRunner:
    """Base para executores de ferramentas externas."""

    def __init__(self, timeout: int = 300) -> None:
        self._timeout = timeout

    def _run(
        self,
        cmd: list[str],
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
    ) -> tuple[int, str, str]:
        """Executa comando e retorna (returncode, stdout, stderr)."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                cwd=cwd,
                env={**os.environ, **(env or {})},
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"TIMEOUT após {self._timeout}s"
        except FileNotFoundError:
            return -2, "", f"Comando não encontrado: {cmd[0]}"
        except Exception as e:
            return -3, "", str(e)

    def is_available(self) -> bool:
        """Verifica se a ferramenta está instalada."""
        raise NotImplementedError


# ─── Soteria ─────────────────────────────────────────────────────────────────

class SoteriaRunner(_ToolRunner):
    """
    Soteria: analisador estático para programas Solana em Rust.
    Detecta: missing signer, integer overflow, account confusion, etc.
    Instalação: cargo install soteria
    """

    def is_available(self) -> bool:
        return shutil.which("soteria") is not None

    def run(self, project_path: str) -> ToolResult:
        t0 = time.monotonic()
        tool = "soteria"

        if not self.is_available():
            return ToolResult(tool=tool, status=ToolStatus.NOT_FOUND, duration_s=0,
                              error="Soteria não instalado. Execute: cargo install soteria")

        rc, stdout, stderr = self._run(
            ["soteria", "--", "--", "-Znext-solver"],
            cwd=project_path,
        )

        duration = time.monotonic() - t0
        output = stdout + "\n" + stderr

        if rc == -1:
            return ToolResult(tool=tool, status=ToolStatus.TIMEOUT, duration_s=duration,
                              raw_output=output, error="Timeout")
        if rc == -2:
            return ToolResult(tool=tool, status=ToolStatus.NOT_FOUND, duration_s=duration,
                              error="Soteria não encontrado no PATH")

        findings = self._parse_output(output)
        return ToolResult(
            tool=tool,
            status=ToolStatus.OK if rc == 0 else ToolStatus.FAILED,
            duration_s=duration,
            findings=findings,
            raw_output=output[:8000],
        )

    def _parse_output(self, output: str) -> list[ToolFinding]:
        """Parseia output do Soteria para extrair findings."""
        findings = []

        # Patterns do Soteria output
        patterns = [
            # "warning[signer_authorization]: Missing signer check at file.rs:42"
            (r"(warning|error)\[(\w+)\]:\s*(.+?)\s+at\s+(\S+):(\d+)",
             lambda m: ToolFinding(
                tool="soteria", severity="high" if m.group(1) == "error" else "medium",
                rule_id=m.group(2), title=m.group(3),
                description=m.group(3), file=m.group(4), line=int(m.group(5)),
             )),
            # "CRITICAL: account_confusion in programs/vault/src/lib.rs:88"
            (r"(CRITICAL|HIGH|MEDIUM|LOW):\s*(.+?)\s+in\s+(\S+):(\d+)",
             lambda m: ToolFinding(
                tool="soteria",
                severity=m.group(1).lower(),
                rule_id=m.group(2).split()[0].lower(),
                title=m.group(2), description=m.group(2),
                file=m.group(3), line=int(m.group(4)),
             )),
        ]

        for pattern, factory in patterns:
            for m in re.finditer(pattern, output, re.IGNORECASE):
                try:
                    findings.append(factory(m))
                except Exception:
                    pass

        # Fallback: detectar palavras-chave suspeitas
        if not findings:
            keywords = {
                "missing signer":     ("SOT-001", "Missing Signer Check",     "high"),
                "account confusion":  ("SOT-002", "Account Confusion",        "critical"),
                "integer overflow":   ("SOT-003", "Integer Overflow",         "high"),
                "arbitrary cpi":      ("SOT-004", "Arbitrary CPI",            "critical"),
                "sysvar_rent":        ("SOT-005", "Deprecated Sysvar Rent",   "low"),
                "reentrancy":         ("SOT-006", "CPI Reentrancy Risk",      "high"),
            }
            for kw, (rule_id, title, sev) in keywords.items():
                if kw in output.lower():
                    findings.append(ToolFinding(
                        tool="soteria", severity=sev, rule_id=rule_id,
                        title=title, description=f"Padrão detectado: '{kw}'",
                    ))

        return findings


# ─── Anchor Linter ────────────────────────────────────────────────────────────

class AnchorLinterRunner(_ToolRunner):
    """
    Anchor Linter: análise estática específica para programas Anchor.
    Verifica: #[account] constraints, signer checks, owner checks.
    Instalação: cargo install anchor-cli
    """

    def is_available(self) -> bool:
        return shutil.which("anchor") is not None

    def run(self, project_path: str) -> ToolResult:
        t0 = time.monotonic()
        tool = "anchor_linter"

        if not self.is_available():
            # Fallback: análise estática manual via regex em Rust
            logger.info("[toolkit] anchor CLI não encontrado — usando análise estática manual")
            return self._manual_anchor_analysis(project_path, t0)

        # Tentar anchor verify
        rc, stdout, stderr = self._run(
            ["anchor", "build", "--", "--deny", "warnings"],
            cwd=project_path,
        )

        duration = time.monotonic() - t0
        output = stdout + "\n" + stderr

        if rc == -2:
            return self._manual_anchor_analysis(project_path, t0)

        findings = self._parse_anchor_output(output)
        return ToolResult(
            tool=tool,
            status=ToolStatus.OK,
            duration_s=duration,
            findings=findings,
            raw_output=output[:8000],
        )

    def _manual_anchor_analysis(self, project_path: str, t0: float) -> ToolResult:
        """Análise estática manual via regex quando anchor CLI não está disponível."""
        findings = []
        path = Path(project_path)

        rust_files = list(path.rglob("*.rs"))
        if not rust_files:
            return ToolResult(
                tool="anchor_linter", status=ToolStatus.SKIPPED,
                duration_s=time.monotonic() - t0,
                error="Nenhum arquivo .rs encontrado",
            )

        checks = [
            # (pattern_ausente, anti_pattern, rule_id, title, severity, description)
            (
                r"#\[account[^\]]*signer[^\]]*\]|ctx\.accounts\.\w+\.is_signer",
                None,
                "ANC-001", "Missing Signer Check", "high",
                "Instrução modifica estado sem verificar assinante válido.",
            ),
            (
                r"\.owner\s*==|check.*owner|owner.*check",
                None,
                "ANC-002", "Missing Owner Check", "high",
                "Conta manipulada sem verificação de ownership.",
            ),
            (
                r"checked_add|checked_sub|checked_mul|checked_div|saturating_",
                None,
                "ANC-003", "Potential Integer Overflow", "medium",
                "Operação aritmética sem verificação de overflow.",
            ),
            (
                r"close\s*=\s*\w+|close\s*:",
                r"force_defund|rent_exempt",
                "ANC-004", "Account Close Without Force-Defund", "medium",
                "Conta fechada sem proteção contra extração de rent.",
            ),
            (
                r"invoke_signed|CpiContext|cpi::",
                r"\.program\s*==|program_id\s*==",
                "ANC-005", "Unchecked CPI Target", "high",
                "CPI sem validação do program ID destino — risco de reentrancy/confusion.",
            ),
            (
                r"Clock::get\(\)|slot_hashes",
                None,
                "ANC-006", "On-Chain Randomness Source", "medium",
                "Uso de clock/slot como fonte de aleatoriedade é manipulável por validadores.",
            ),
        ]

        for rust_file in rust_files:
            try:
                content = rust_file.read_text("utf-8", errors="ignore")
                file_rel = str(rust_file.relative_to(path))

                for (good_pattern, bad_pattern, rule_id, title, sev, desc) in checks:
                    has_risky = re.search(r"pub fn \w+.*Context|#\[program\]", content)
                    if not has_risky:
                        continue
                    has_protection = re.search(good_pattern, content, re.IGNORECASE)
                    has_bad = bad_pattern and re.search(bad_pattern, content, re.IGNORECASE)

                    should_flag = (not has_protection) or (bad_pattern and not has_bad)
                    if should_flag and (rule_id in ("ANC-003", "ANC-006")):
                        # Estes só flaggam se o padrão AUSENTE é a salvaguarda
                        risky_op = {
                            "ANC-003": r"(\w+\s*[+\-\*]\s*\w+)",
                            "ANC-006": r"(Clock::get|slot_hashes)",
                        }.get(rule_id)
                        if risky_op and not re.search(risky_op, content):
                            continue

                    if should_flag:
                        # Encontrar linha aproximada
                        line_num = None
                        for i, line in enumerate(content.splitlines(), 1):
                            if re.search(good_pattern or "", line, re.IGNORECASE):
                                line_num = i
                                break

                        findings.append(ToolFinding(
                            tool="anchor_linter",
                            severity=sev,
                            rule_id=rule_id,
                            title=title,
                            description=desc,
                            file=file_rel,
                            line=line_num,
                        ))

            except Exception as e:
                logger.debug(f"[toolkit] Erro ao analisar {rust_file}: {e}")

        return ToolResult(
            tool="anchor_linter",
            status=ToolStatus.OK,
            duration_s=time.monotonic() - t0,
            findings=findings,
            raw_output=f"Análise estática manual: {len(rust_files)} arquivos Rust",
        )

    def _parse_anchor_output(self, output: str) -> list[ToolFinding]:
        findings = []
        for line in output.splitlines():
            m = re.match(r"(warning|error)(\[E\d+\])?:\s*(.+?)(?:\s+-->\s+(\S+):(\d+))?$", line)
            if m:
                sev = "high" if m.group(1) == "error" else "low"
                findings.append(ToolFinding(
                    tool="anchor_linter", severity=sev,
                    rule_id=m.group(2) or "ANC-000", title=m.group(3),
                    description=m.group(3),
                    file=m.group(4), line=int(m.group(5)) if m.group(5) else None,
                ))
        return findings


# ─── Trident Fuzzer ───────────────────────────────────────────────────────────

class TridentRunner(_ToolRunner):
    """
    Trident: framework de fuzzing para programas Anchor.
    Gera inputs aleatórios e verifica invariantes (propriedades).
    Instalação: cargo install trident-cli
    """

    def is_available(self) -> bool:
        return shutil.which("trident") is not None

    def run(
        self,
        project_path: str,
        fuzz_duration_s: int = 60,
        max_crashes: int = 5,
    ) -> ToolResult:
        t0 = time.monotonic()
        tool = "trident"

        if not self.is_available():
            return ToolResult(
                tool=tool, status=ToolStatus.NOT_FOUND, duration_s=0,
                error=(
                    "Trident não instalado. Execute:\n"
                    "  cargo install trident-cli\n"
                    "  cd <projeto> && trident init"
                ),
            )

        # Inicializar Trident se não tiver fuzz/ dir
        fuzz_dir = Path(project_path) / "trident-tests"
        if not fuzz_dir.exists():
            logger.info("[toolkit] Inicializando Trident no projeto...")
            rc, _, stderr = self._run(["trident", "init"], cwd=project_path, env={"RUST_LOG": "off"})
            if rc != 0:
                return ToolResult(
                    tool=tool, status=ToolStatus.FAILED, duration_s=time.monotonic() - t0,
                    error=f"trident init falhou: {stderr[:500]}",
                )

        # Executar fuzzing com limite de tempo
        rc, stdout, stderr = self._run(
            ["trident", "fuzz", "run-hfuzz",
             "--", f"--max_total_time={fuzz_duration_s}",
             f"--max_number_of_runs={max_crashes * 100}"],
            cwd=project_path,
            env={"RUST_LOG": "warn"},
        )

        duration = time.monotonic() - t0
        output = stdout + "\n" + stderr

        findings = self._parse_output(output, project_path)
        return ToolResult(
            tool=tool,
            status=ToolStatus.OK,
            duration_s=duration,
            findings=findings,
            raw_output=output[:8000],
        )

    def _parse_output(self, output: str, project_path: str) -> list[ToolFinding]:
        """Parseia crashes do Trident."""
        findings = []

        crash_patterns = [
            r"CRASH:\s*(.+)",
            r"panicked at '(.+?)'",
            r"AddressSanitizer:.+",
            r"SCARECROW:.+",
        ]

        for pattern in crash_patterns:
            for m in re.finditer(pattern, output, re.IGNORECASE):
                findings.append(ToolFinding(
                    tool="trident",
                    severity="high",
                    rule_id="TRI-001",
                    title=f"Fuzzing Crash: {m.group(0)[:80]}",
                    description=(
                        f"O fuzzer Trident encontrou um input que causa crash/panic:\n"
                        f"{m.group(0)}"
                    ),
                    ref="https://ackee.xyz/trident/docs/",
                ))

        # Verificar pasta de crashes
        crash_dir = Path(project_path) / "trident-tests" / "hfuzz_workspace"
        if crash_dir.exists():
            crash_files = list(crash_dir.rglob("*.fuzz"))[:5]
            for cf in crash_files:
                if cf.stat().st_size > 0:
                    findings.append(ToolFinding(
                        tool="trident",
                        severity="high",
                        rule_id="TRI-002",
                        title=f"Crash input salvo: {cf.name}",
                        description=f"Input de crash em: {cf}",
                        file=str(cf),
                    ))

        return findings


# ─── Cargo Audit ──────────────────────────────────────────────────────────────

class CargoAuditRunner(_ToolRunner):
    """
    cargo-audit: verifica CVEs em dependências Rust.
    Instalação: cargo install cargo-audit
    """

    def is_available(self) -> bool:
        return shutil.which("cargo-audit") is not None or shutil.which("cargo") is not None

    def run(self, project_path: str) -> ToolResult:
        t0 = time.monotonic()
        tool = "cargo_audit"

        cmd = ["cargo", "audit", "--json"]
        rc, stdout, stderr = self._run(cmd, cwd=project_path)
        duration = time.monotonic() - t0

        if rc == -2:
            return ToolResult(
                tool=tool, status=ToolStatus.NOT_FOUND, duration_s=duration,
                error="cargo não encontrado no PATH",
            )

        findings = []
        try:
            data = json.loads(stdout)
            for vuln in data.get("vulnerabilities", {}).get("list", []):
                adv = vuln.get("advisory", {})
                pkg = vuln.get("package", {})
                findings.append(ToolFinding(
                    tool=tool,
                    severity="high" if adv.get("cvss") and float(adv.get("cvss", {}).get("base_score", 0) or 0) >= 7.0 else "medium",
                    rule_id=adv.get("id", "CVE-UNKNOWN"),
                    title=adv.get("title", "Vulnerabilidade em dependência"),
                    description=(
                        f"Pacote: {pkg.get('name')}@{pkg.get('version')}\n"
                        f"CVE: {adv.get('id')}\n"
                        f"{adv.get('description', '')}"
                    ),
                    cwe=adv.get("categories", [""])[0] if adv.get("categories") else None,
                    ref=adv.get("url"),
                ))
        except (json.JSONDecodeError, KeyError):
            # Fallback: parsear output de texto
            for line in (stdout + stderr).splitlines():
                if "error[" in line.lower() or "warning[" in line.lower():
                    findings.append(ToolFinding(
                        tool=tool, severity="medium", rule_id="CARGO-001",
                        title=line[:120], description=line,
                    ))

        return ToolResult(
            tool=tool,
            status=ToolStatus.OK if rc == 0 else ToolStatus.FAILED,
            duration_s=duration,
            findings=findings,
            raw_output=(stdout + stderr)[:4000],
        )


# ─── Solana Program Test ──────────────────────────────────────────────────────

class SolanaProgramTestRunner(_ToolRunner):
    """
    Executa `cargo test` e `anchor test` no contexto do Solana-Program-Test.
    Captura panics e failures como findings.
    """

    def is_available(self) -> bool:
        return shutil.which("cargo") is not None

    def run(
        self,
        project_path: str,
        test_filter: Optional[str] = None,
        use_anchor: bool = False,
    ) -> ToolResult:
        t0 = time.monotonic()
        tool = "solana_program_test"

        if use_anchor and shutil.which("anchor"):
            cmd = ["anchor", "test", "--skip-local-validator"]
        else:
            cmd = ["cargo", "test", "--", "--nocapture"]
            if test_filter:
                cmd += [test_filter]

        rc, stdout, stderr = self._run(cmd, cwd=project_path,
                                       env={"RUST_BACKTRACE": "1", "RUST_LOG": "solana=warn"})
        duration = time.monotonic() - t0
        output = stdout + "\n" + stderr

        findings = self._parse_test_output(output)
        return ToolResult(
            tool=tool,
            status=ToolStatus.OK if rc == 0 else ToolStatus.FAILED,
            duration_s=duration,
            findings=findings,
            raw_output=output[:8000],
        )

    def _parse_test_output(self, output: str) -> list[ToolFinding]:
        findings = []

        # Panics
        for m in re.finditer(r"panicked at '(.+?)'\s*,\s*(\S+):(\d+)", output):
            findings.append(ToolFinding(
                tool="solana_program_test",
                severity="high",
                rule_id="SPT-001",
                title=f"Panic: {m.group(1)[:80]}",
                description=m.group(1),
                file=m.group(2),
                line=int(m.group(3)),
            ))

        # Test failures
        for m in re.finditer(r"FAILED\s+(\S+)\s+-\s+(.+)", output):
            findings.append(ToolFinding(
                tool="solana_program_test",
                severity="medium",
                rule_id="SPT-002",
                title=f"Test Failed: {m.group(1)}",
                description=m.group(2),
            ))

        # Custom program errors
        for m in re.finditer(r"Custom program error: (0x[0-9a-fA-F]+)", output):
            findings.append(ToolFinding(
                tool="solana_program_test",
                severity="medium",
                rule_id="SPT-003",
                title=f"Custom Error Code: {m.group(1)}",
                description=f"Programa retornou código de erro: {m.group(1)}",
            ))

        return findings


# ─── Audit Toolkit Orchestrator ───────────────────────────────────────────────

class AuditToolkit:
    """
    Orquestrador de todas as ferramentas de auditoria.

    Uso:
        tk = AuditToolkit()
        report = tk.run_all(project_path="/path/to/anchor-program")
        print(report.all_findings)
    """

    def __init__(
        self,
        timeout: int = 300,
        run_fuzzer: bool = False,
        fuzz_duration: int = 60,
    ) -> None:
        self._timeout = timeout
        self._run_fuzzer = run_fuzzer
        self._fuzz_duration = fuzz_duration

        self._soteria = SoteriaRunner(timeout)
        self._anchor  = AnchorLinterRunner(timeout)
        self._trident = TridentRunner(timeout + fuzz_duration)
        self._cargo_audit = CargoAuditRunner(timeout)
        self._spt = SolanaProgramTestRunner(timeout)

    def available_tools(self) -> dict[str, bool]:
        return {
            "soteria":              self._soteria.is_available(),
            "anchor_linter":        self._anchor.is_available(),
            "trident":              self._trident.is_available() and self._run_fuzzer,
            "cargo_audit":          self._cargo_audit.is_available(),
            "solana_program_test":  self._spt.is_available(),
        }

    def run_all(
        self,
        project_path: str,
        tools: Optional[list[str]] = None,
    ) -> ToolkitReport:
        """
        Executa todas as ferramentas disponíveis em sequência.

        Args:
            project_path: Caminho para o projeto Solana/Anchor.
            tools: Lista de ferramentas a executar (None = todas).
        """
        path = Path(project_path)
        if not path.exists():
            raise FileNotFoundError(f"Projeto não encontrado: {project_path}")

        t0 = time.monotonic()
        results: list[ToolResult] = []
        tools_run: list[str] = []

        available = self.available_tools()
        logger.info(f"[toolkit] Ferramentas disponíveis: {available}")

        tool_map = [
            ("anchor_linter",       self._anchor.run),
            ("cargo_audit",         self._cargo_audit.run),
            ("soteria",             self._soteria.run),
            ("solana_program_test", lambda p: self._spt.run(p)),
        ]

        if self._run_fuzzer:
            tool_map.append(("trident", lambda p: self._trident.run(p, self._fuzz_duration)))

        for tool_name, runner in tool_map:
            if tools and tool_name not in tools:
                continue
            logger.info(f"[toolkit] Executando {tool_name}...")
            try:
                result = runner(str(path))
                results.append(result)
                tools_run.append(tool_name)
                logger.info(
                    f"[toolkit] {tool_name}: {result.status}  "
                    f"findings={len(result.findings)}  t={result.duration_s:.1f}s"
                )
            except Exception as e:
                logger.error(f"[toolkit] Erro em {tool_name}: {e}")
                results.append(ToolResult(
                    tool=tool_name, status=ToolStatus.FAILED,
                    duration_s=0, error=str(e),
                ))
                tools_run.append(tool_name)

        return ToolkitReport(
            project_path=str(path),
            ran_at=t0,
            tools_run=tools_run,
            results=results,
            total_time_s=time.monotonic() - t0,
        )

    def run_fast(self, project_path: str) -> ToolkitReport:
        """
        Análise rápida (sem Trident): Anchor Linter + Cargo Audit.
        Ideal para Tier-1 triage — resultado em segundos.
        """
        return self.run_all(project_path, tools=["anchor_linter", "cargo_audit"])
