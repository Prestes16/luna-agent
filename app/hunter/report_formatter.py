"""
Luna Report Formatter
======================
Gera relatórios de vulnerabilidades no padrão Immunefi.

Estrutura padrão Immunefi:
  1. Title (título objetivo, sem hype)
  2. Severity (Critical/High/Medium/Low)
  3. Summary (1-2 parágrafos: o que é e o impacto)
  4. Vulnerability Details (análise técnica)
  5. Impact (consequências concretas)
  6. Proof of Concept (passos + código)
  7. Recommended Fix (patch code)
  8. References (links, CVEs, papers)

Referência: https://immunefi.com/learn/bug-bounty-vulnerability-report/
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ─── Severidade Immunefi ──────────────────────────────────────────────────────

class ImmunefisSeverity(str, Enum):
    CRITICAL = "Critical"
    HIGH     = "High"
    MEDIUM   = "Medium"
    LOW      = "Low"
    NONE     = "None"


# Faixas de recompensa Immunefi (USD) por severidade
IMMUNEFI_REWARD_RANGES: dict[ImmunefisSSeverity, str] = {
    ImmunefisSSeverity.CRITICAL: "$50,000 – $10,000,000+",
    ImmunefisSSeverity.HIGH:     "$10,000 – $100,000",
    ImmunefisSSeverity.MEDIUM:   "$1,000 – $20,000",
    ImmunefisSSeverity.LOW:      "$1,000 – $5,000",
    ImmunefisSSeverity.NONE:     "N/A",
}


class ImmunefisSSeverity(str, Enum):
    CRITICAL = "Critical"
    HIGH     = "High"
    MEDIUM   = "Medium"
    LOW      = "Low"
    NONE     = "None"


IMMUNEFI_REWARD_RANGES: dict[ImmunefisSSeverity, str] = {
    ImmunefisSSeverity.CRITICAL: "$50,000 – $10,000,000+",
    ImmunefisSSeverity.HIGH:     "$10,000 – $100,000",
    ImmunefisSSeverity.MEDIUM:   "$1,000 – $20,000",
    ImmunefisSSeverity.LOW:      "$1,000 – $5,000",
    ImmunefisSSeverity.NONE:     "N/A",
}


# ─── Estrutura do relatório ───────────────────────────────────────────────────

@dataclass
class VulnerabilityDetails:
    """Detalhes técnicos de uma vulnerabilidade para o relatório."""
    vuln_id:          str              # Ex: "LUNA-2024-001"
    title:            str
    severity:         ImmunefisSSeverity
    program_id:       Optional[str]   = None
    target_contract:  Optional[str]   = None   # nome do programa/contrato
    affected_function: Optional[str]  = None
    cwe:              Optional[str]   = None   # ex: "CWE-284"
    cvss_score:       Optional[float] = None
    summary:          str             = ""
    technical_details: str            = ""
    root_cause:       str             = ""
    impact:           str             = ""
    poc_code:         str             = ""
    poc_steps:        list[str]       = field(default_factory=list)
    fix:              str             = ""
    fix_diff:         str             = ""      # diff format
    references:       list[str]       = field(default_factory=list)
    affected_files:   list[str]       = field(default_factory=list)
    tvl_at_risk_usd:  Optional[float] = None    # fundos em risco
    notes:            str             = ""


@dataclass
class ImmunefiBountyReport:
    """Relatório completo no padrão Immunefi."""
    protocol_name:  str
    protocol_url:   Optional[str]
    bounty_program: Optional[str]
    findings:       list[VulnerabilityDetails]
    researcher:     str = "Luna Hunter-V2 (Autonomous Security Agent)"
    generated_at:   float = field(default_factory=time.time)
    network:        str = "Solana Mainnet"
    chain_id:       Optional[str] = None

    def render_markdown(self) -> str:
        """Renderiza relatório completo em Markdown."""
        lines = [self._header()]
        for finding in self.findings:
            lines.append(self._finding_section(finding))
        lines.append(self._footer())
        return "\n".join(lines)

    def render_json(self) -> str:
        """Renderiza em JSON para submissão programática."""
        return json.dumps({
            "protocol": self.protocol_name,
            "bounty_program": self.bounty_program,
            "researcher": self.researcher,
            "network": self.network,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.generated_at)),
            "findings": [
                {
                    "id":               f.vuln_id,
                    "title":            f.title,
                    "severity":         f.severity.value,
                    "program_id":       f.program_id,
                    "affected_function": f.affected_function,
                    "cwe":              f.cwe,
                    "cvss":             f.cvss_score,
                    "summary":          f.summary,
                    "impact":           f.impact,
                    "tvl_at_risk_usd":  f.tvl_at_risk_usd,
                    "has_poc":          bool(f.poc_code or f.poc_steps),
                    "has_fix":          bool(f.fix or f.fix_diff),
                }
                for f in self.findings
            ],
            "total_findings": len(self.findings),
            "severity_breakdown": {
                sev.value: sum(1 for f in self.findings if f.severity == sev)
                for sev in ImmunefisSSeverity
            },
        }, indent=2, ensure_ascii=False)

    def _header(self) -> str:
        total = len(self.findings)
        critical = sum(1 for f in self.findings if f.severity == ImmunefisSSeverity.CRITICAL)
        high = sum(1 for f in self.findings if f.severity == ImmunefisSSeverity.HIGH)
        date_str = time.strftime("%B %d, %Y", time.gmtime(self.generated_at))

        breakdown_lines = []
        for sev in (ImmunefisSSeverity.CRITICAL, ImmunefisSSeverity.HIGH,
                    ImmunefisSSeverity.MEDIUM, ImmunefisSSeverity.LOW):
            count = sum(1 for f in self.findings if f.severity == sev)
            if count:
                breakdown_lines.append(f"| {sev.value} | {count} |")

        breakdown = "\n".join(breakdown_lines) if breakdown_lines else "| None | 0 |"

        tvl_risks = [f.tvl_at_risk_usd for f in self.findings if f.tvl_at_risk_usd]
        tvl_line = (
            f"\n**Estimated Funds at Risk:** ${max(tvl_risks):,.0f} USD"
            if tvl_risks else ""
        )

        return f"""\
# Security Vulnerability Report

**Protocol:** {self.protocol_name}
**Network:** {self.network}
**Date:** {date_str}
**Researcher:** {self.researcher}
{f"**Bounty Program:** [{self.bounty_program}](https://immunefi.com/bounty/{self.protocol_name.lower()}/)" if self.bounty_program else ""}
{tvl_line}

---

## Executive Summary

This report documents **{total} security vulnerabilities** identified in the {self.protocol_name} protocol on {self.network}. The analysis was performed using automated static analysis (Soteria, Anchor-Linter), fuzzing (Trident), and manual code review.

### Severity Breakdown

| Severity | Count |
|----------|-------|
{breakdown}

---
"""

    def _finding_section(self, f: VulnerabilityDetails) -> str:
        severity_emoji = {
            ImmunefisSSeverity.CRITICAL: "🚨",
            ImmunefisSSeverity.HIGH:     "❌",
            ImmunefisSSeverity.MEDIUM:   "⚠️",
            ImmunefisSSeverity.LOW:      "ℹ️",
            ImmunefisSSeverity.NONE:     "💡",
        }.get(f.severity, "🔍")

        reward_range = IMMUNEFI_REWARD_RANGES.get(f.severity, "N/A")

        poc_section = ""
        if f.poc_code or f.poc_steps:
            steps_text = ""
            if f.poc_steps:
                steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(f.poc_steps))
            code_block = f"\n```typescript\n{f.poc_code}\n```" if f.poc_code else ""
            poc_section = f"""
### Proof of Concept

{steps_text}
{code_block}
"""

        fix_section = ""
        if f.fix or f.fix_diff:
            diff_block = f"\n```diff\n{f.fix_diff}\n```" if f.fix_diff else ""
            fix_section = f"""
### Recommended Fix

{f.fix}
{diff_block}
"""

        files_section = ""
        if f.affected_files:
            files_section = "\n**Affected Files:**\n" + "\n".join(f"- `{fp}`" for fp in f.affected_files)

        refs_section = ""
        if f.references:
            refs_section = "\n**References:**\n" + "\n".join(f"- {r}" for r in f.references)

        tvl_section = (
            f"\n**Estimated Funds at Risk:** ${f.tvl_at_risk_usd:,.0f} USD\n"
            if f.tvl_at_risk_usd else ""
        )

        cwe_line = f"**CWE:** {f.cwe}  " if f.cwe else ""
        cvss_line = f"**CVSS:** {f.cvss_score}  " if f.cvss_score else ""
        func_line = (f"**Affected Function:** `{f.affected_function}`  "
                     if f.affected_function else "")
        program_line = (f"**Program ID:** `{f.program_id}`  "
                        if f.program_id else "")

        return f"""
---

## {severity_emoji} [{f.severity.value}] {f.title}

**ID:** `{f.vuln_id}`
**Severity:** **{f.severity.value}** (Immunefi Reward Range: {reward_range})
{program_line}
{func_line}
{cwe_line}
{cvss_line}
{tvl_section}
{files_section}

### Summary

{f.summary}

### Vulnerability Details

{f.technical_details}

### Root Cause

{f.root_cause}

### Impact

{f.impact}
{poc_section}
{fix_section}
{refs_section}
"""

    def _footer(self) -> str:
        return f"""
---

## Disclosure Policy

This report follows responsible disclosure practices. The findings were identified through authorized security research and reported to the protocol team.

**Timeline:**
- Discovery: {time.strftime("%Y-%m-%d", time.gmtime(self.generated_at))}
- Report Generated: {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(self.generated_at))}

---

*Generated by Luna Hunter-V2 Elite — Autonomous Web3 Security Agent*
*Analysis powered by: Soteria, Anchor-Linter, Trident, Luna LLM Router*
"""


# ─── Factory de relatórios ────────────────────────────────────────────────────

class ReportFormatter:
    """
    Converte findings de AuditEngine/AuditToolkit para relatório Immunefi.
    """

    def __init__(self, protocol_name: str = "Unknown Protocol") -> None:
        self._protocol = protocol_name
        self._vuln_counter = 0

    def _next_id(self) -> str:
        self._vuln_counter += 1
        year = time.strftime("%Y")
        return f"LUNA-{year}-{self._vuln_counter:03d}"

    def _map_severity(self, sev: str) -> ImmunefisSSeverity:
        mapping = {
            "critical": ImmunefisSSeverity.CRITICAL,
            "high":     ImmunefisSSeverity.HIGH,
            "medium":   ImmunefisSSeverity.MEDIUM,
            "low":      ImmunefisSSeverity.LOW,
            "info":     ImmunefisSSeverity.NONE,
        }
        return mapping.get(sev.lower(), ImmunefisSSeverity.LOW)

    def from_audit_findings(
        self,
        findings: list,  # list[Finding] from audit_engine
        protocol_name: Optional[str] = None,
        program_id: Optional[str] = None,
        tvl_usd: Optional[float] = None,
        poc_map: Optional[dict[str, str]] = None,  # rule_id → poc_code
    ) -> ImmunefiBountyReport:
        """
        Cria relatório Immunefi a partir de findings do AuditEngine.

        Args:
            findings: Lista de Finding do AuditEngine.
            protocol_name: Nome do protocolo.
            program_id: Endereço do programa.
            tvl_usd: Total Value Locked do protocolo.
            poc_map: Mapeamento de rule_id → código PoC gerado.
        """
        protocol = protocol_name or self._protocol
        self._protocol = protocol
        vulns: list[VulnerabilityDetails] = []

        for f in findings:
            if not hasattr(f, "severity"):
                continue
            sev = self._map_severity(f.severity if isinstance(f.severity, str) else f.severity.value)

            technical = f.description if hasattr(f, "description") else ""
            if hasattr(f, "snippet") and f.snippet:
                technical += f"\n\nCode snippet:\n```rust\n{f.snippet}\n```"

            # Calcular TVL estimado em risco por severidade
            tvl_at_risk = None
            if tvl_usd:
                tvl_fractions = {
                    ImmunefisSSeverity.CRITICAL: 1.0,
                    ImmunefisSSeverity.HIGH: 0.3,
                    ImmunefisSSeverity.MEDIUM: 0.1,
                    ImmunefisSSeverity.LOW: 0.0,
                }
                frac = tvl_fractions.get(sev, 0)
                tvl_at_risk = tvl_usd * frac if frac > 0 else None

            poc_code = ""
            if poc_map and hasattr(f, "rule_id"):
                poc_code = poc_map.get(f.rule_id, "")

            file_loc = ""
            if hasattr(f, "file") and f.file:
                line_part = f":{f.line}" if hasattr(f, "line") and f.line else ""
                file_loc = f"{f.file}{line_part}"

            recommendation = ""
            if hasattr(f, "recommendation"):
                recommendation = f.recommendation

            vuln = VulnerabilityDetails(
                vuln_id=self._next_id(),
                title=f.title if hasattr(f, "title") else str(f),
                severity=sev,
                program_id=program_id,
                affected_function=None,
                cwe=_rule_to_cwe(f.rule_id if hasattr(f, "rule_id") else ""),
                summary=technical[:300] + ("..." if len(technical) > 300 else ""),
                technical_details=technical,
                root_cause=_rule_to_root_cause(f.rule_id if hasattr(f, "rule_id") else ""),
                impact=_severity_to_impact(sev, f.title if hasattr(f, "title") else ""),
                poc_code=poc_code,
                fix=recommendation,
                affected_files=[file_loc] if file_loc else [],
                tvl_at_risk_usd=tvl_at_risk,
                references=_rule_to_refs(f.rule_id if hasattr(f, "rule_id") else ""),
            )
            vulns.append(vuln)

        return ImmunefiBountyReport(
            protocol_name=protocol,
            protocol_url=None,
            bounty_program=protocol,
            findings=vulns,
            network="Solana Mainnet",
        )

    def from_llm_analysis(
        self,
        llm_output: str,
        program_id: Optional[str] = None,
        protocol_name: Optional[str] = None,
    ) -> ImmunefiBountyReport:
        """
        Parseia output do LLM (análise deep) para estrutura de relatório.
        Espera que o LLM tenha formatado usando seções bem definidas.
        """
        protocol = protocol_name or self._protocol
        vulns: list[VulnerabilityDetails] = []

        # Parsear seções do LLM
        sections = _parse_llm_sections(llm_output)

        for sec in sections:
            sev_str = sec.get("severity", "medium")
            vuln = VulnerabilityDetails(
                vuln_id=self._next_id(),
                title=sec.get("title", "Vulnerabilidade Detectada"),
                severity=self._map_severity(sev_str),
                program_id=program_id,
                summary=sec.get("summary", ""),
                technical_details=sec.get("details", ""),
                root_cause=sec.get("root_cause", ""),
                impact=sec.get("impact", ""),
                poc_code=sec.get("poc", ""),
                fix=sec.get("fix", ""),
                references=sec.get("refs", []),
            )
            vulns.append(vuln)

        return ImmunefiBountyReport(
            protocol_name=protocol,
            protocol_url=None,
            bounty_program=protocol,
            findings=vulns,
        )

    def save(
        self,
        report: ImmunefiBountyReport,
        output_dir: str,
        formats: Optional[list[str]] = None,
    ) -> list[Path]:
        """Salva relatório em arquivo(s)."""
        if formats is None:
            formats = ["markdown", "json"]

        base = Path(output_dir)
        base.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        saved: list[Path] = []

        if "markdown" in formats:
            p = base / f"immunefi_report_{ts}.md"
            p.write_text(report.render_markdown(), encoding="utf-8")
            saved.append(p)

        if "json" in formats:
            p = base / f"immunefi_report_{ts}.json"
            p.write_text(report.render_json(), encoding="utf-8")
            saved.append(p)

        return saved


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _rule_to_cwe(rule_id: str) -> Optional[str]:
    mapping = {
        "SOL-001": "CWE-284",   # Missing Signer → Improper Access Control
        "SOL-002": "CWE-284",   # Owner Check
        "SOL-003": "CWE-190",   # Overflow → Integer Overflow
        "SOL-004": "CWE-330",   # PDA Bump → Use of Insufficiently Random Values
        "SOL-005": "CWE-841",   # CPI Reentrancy → Improper Enforcement of Sequence
        "SOL-006": "CWE-330",   # Randomness
        "EVM-001": "CWE-841",   # Reentrancy
        "EVM-002": "CWE-284",   # tx.origin
        "ANC-001": "CWE-284",
        "ANC-002": "CWE-284",
        "ANC-003": "CWE-190",
    }
    return mapping.get(rule_id.upper())


def _rule_to_root_cause(rule_id: str) -> str:
    causes = {
        "SOL-001": "A instrução não verifica se o campo `authority` ou equivalente tem `is_signer = true`.",
        "SOL-002": "A conta é aceita sem verificar se `account.owner == expected_program_id`.",
        "SOL-003": "Operação aritmética realizada sem `checked_add`/`checked_sub`, permitindo wrap-around em u64.",
        "SOL-004": "O bump seed armazenado não é o bump canônico, permitindo colisão de PDA.",
        "SOL-005": "Estado não é atualizado antes de realizar CPI, criando window de reentrancy.",
        "ANC-001": "Constraint `#[account(signer)]` ausente ou validação manual faltando.",
        "ANC-002": "Constraint `#[account(owner = program_id)]` ausente.",
        "ANC-003": "Operação aritmética sem `checked_*` ou `saturating_*`.",
    }
    return causes.get(rule_id.upper(), "Analise o código-fonte para identificar a causa raiz.")


def _severity_to_impact(sev: ImmunefisSSeverity, title: str) -> str:
    if sev == ImmunefisSSeverity.CRITICAL:
        return (
            f"Um atacante pode explorar esta vulnerabilidade para drenar fundos do protocolo, "
            f"escalar privilégios ou comprometer a integridade do estado on-chain. "
            f"Todos os fundos gerenciados pelo programa estão em risco direto."
        )
    if sev == ImmunefisSSeverity.HIGH:
        return (
            f"Um atacante pode executar ações não autorizadas que resultam em perda parcial "
            f"de fundos, manipulação de estado, ou bypass de controles de acesso críticos."
        )
    if sev == ImmunefisSSeverity.MEDIUM:
        return (
            f"A vulnerabilidade permite que um atacante manipule o estado do protocolo de forma "
            f"inesperada, potencialmente causando perda de fundos em cenários específicos."
        )
    return "Impacto limitado — afeta funcionalidade mas não representa risco imediato de perda de fundos."


def _rule_to_refs(rule_id: str) -> list[str]:
    refs = {
        "SOL-001": [
            "https://book.anchor-lang.com/anchor_in_depth/milestone_project_tic-tac-toe/gameplay.html#adding-validation",
            "https://blog.neodyme.io/posts/solana_common_pitfalls/",
        ],
        "SOL-003": [
            "https://doc.rust-lang.org/std/primitive.u64.html#method.checked_add",
            "https://solanacookbook.com/references/programs.html#how-to-handle-arithmetic",
        ],
        "SOL-005": [
            "https://blog.neodyme.io/posts/solana_reentrancy/",
            "https://osec.io/blog/reentrancy-in-anchor",
        ],
        "EVM-001": [
            "https://swcregistry.io/docs/SWC-107",
            "https://consensys.github.io/smart-contract-best-practices/attacks/reentrancy/",
        ],
    }
    return refs.get(rule_id.upper(), [])


def _parse_llm_sections(text: str) -> list[dict]:
    """
    Parseia output estruturado do LLM para lista de vulnerabilidades.
    O LLM deve usar seções delimitadas por cabeçalhos ou JSON.
    """
    # Tentar parsear como JSON primeiro
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "findings" in data:
            return data["findings"]
    except json.JSONDecodeError:
        pass

    # Parsear markdown com seções
    sections = []
    current: dict = {}

    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith("## ") and current:
            sections.append(current)
            current = {"title": line[3:].strip()}
        elif line.lower().startswith("severity:"):
            current["severity"] = line.split(":", 1)[1].strip().lower()
        elif line.lower().startswith("summary:"):
            current["summary"] = line.split(":", 1)[1].strip()
        elif line.lower().startswith("impact:"):
            current["impact"] = line.split(":", 1)[1].strip()
        elif line.lower().startswith("fix:"):
            current["fix"] = line.split(":", 1)[1].strip()

    if current:
        sections.append(current)

    return sections
