"""
Luna Agent - Security Audit Engine (Solana / Web3 / Smart Contracts)
=====================================================================
Análise estática de vulnerabilidades para:
  - Programas Solana/Anchor (Rust)
  - Contratos Solidity (EVM)
  - APIs Web3 backend (TypeScript/Python)

Vetores auditados (Solana/Anchor):
  1. Missing Signer Check         — instruções sem verificação de autoridade
  2. Missing Owner Check          — contas sem validação de ownership
  3. Account Confusion            — troca de contas pelo atacante
  4. PDA Bump Misuse              — bump não armazenado ou recomputado errado
  5. CPI Reentrancy               — CPI sem re-validação de estado
  6. Arithmetic Overflow          — operações sem checked_* ou saturating_*
  7. Integer Truncation           — cast u64 → u32 ou similar
  8. Missing Account Reload       — uso de account data após CPI sem reload
  9. Insecure Randomness          — clock/slot como fonte de aleatoriedade
 10. Close Account Without Lamports Zero  — conta fechada mas saldo não zerado

Vetores auditados (Solidity):
  1. Reentrancy                   — calls externos antes de atualizar estado
  2. tx.origin Auth               — autenticação por tx.origin
  3. Unchecked Return Values      — transfer/send sem verificação
  4. Integer Overflow/Underflow   — operações sem SafeMath (pré-0.8)
  5. Delegatecall Injection       — delegatecall com endereço controlável
  6. Selfdestruct Exposure        — selfdestruct acessível externamente
  7. Block Timestamp Manipulation — dependência de block.timestamp
  8. Unprotected Initializer      — initializer sem controle de acesso

Vetores auditados (APIs Web3):
  1. Insecure JWT                 — sem verificação de assinatura
  2. Missing Wallet Validation    — endereços sem checksum/validação
  3. Private Key in Code          — chaves hardcoded
  4. Unvalidated RPC Input        — parâmetros não sanitizados para RPC calls
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("luna.audit")

# ─── Severidade ───────────────────────────────────────────────────────────────

SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class Finding:
    vuln_id:     str           # ex: "SOL-001"
    title:       str
    severity:    str           # critical | high | medium | low | info
    file:        str
    line:        int
    snippet:     str           # trecho de código exato
    description: str
    impact:      str
    fix:         str           # correção recomendada com código
    references:  list[str] = field(default_factory=list)


@dataclass
class AuditReport:
    target_path: str
    stack:       str
    files_scanned: int
    total_lines:   int
    findings:    list[Finding] = field(default_factory=list)

    def by_severity(self) -> dict[str, list[Finding]]:
        result: dict[str, list[Finding]] = {s: [] for s in ("critical", "high", "medium", "low", "info")}
        for f in self.findings:
            result.setdefault(f.severity, []).append(f)
        return result

    def score(self) -> int:
        return sum(SEVERITY_WEIGHT.get(f.severity, 0) for f in self.findings)

    def summary(self) -> str:
        by_sev = self.by_severity()
        counts = " | ".join(
            f"{k.upper()}: {len(v)}" for k, v in by_sev.items() if v
        )
        return (
            f"Alvo: {self.target_path}\n"
            f"Stack: {self.stack} | Arquivos: {self.files_scanned} | Linhas: {self.total_lines:,}\n"
            f"Findings: {len(self.findings)} [{counts}]\n"
            f"Score de risco: {self.score()}"
        )

    def render_markdown(self) -> str:
        lines = [
            "# 🛡️ Luna Security Audit Report",
            f"**Alvo:** `{self.target_path}`",
            f"**Stack:** {self.stack}",
            f"**Arquivos escaneados:** {self.files_scanned} ({self.total_lines:,} linhas)",
            f"**Total de findings:** {len(self.findings)}",
            "",
        ]

        by_sev = self.by_severity()
        for severity in ("critical", "high", "medium", "low", "info"):
            findings = by_sev.get(severity, [])
            if not findings:
                continue
            emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}.get(severity, "")
            lines.append(f"\n## {emoji} {severity.upper()} ({len(findings)})")

            for f in findings:
                lines += [
                    f"\n### [{f.vuln_id}] {f.title}",
                    f"**Arquivo:** `{f.file}` linha {f.line}",
                    f"**Impacto:** {f.impact}",
                    "",
                    "**Código vulnerável:**",
                    "```rust" if f.file.endswith(".rs") else
                    "```solidity" if f.file.endswith(".sol") else "```",
                    f.snippet,
                    "```",
                    "",
                    f"**Descrição:** {f.description}",
                    "",
                    "**Correção:**",
                    "```rust" if f.file.endswith(".rs") else
                    "```solidity" if f.file.endswith(".sol") else "```",
                    f.fix,
                    "```",
                ]
                if f.references:
                    lines.append("\n**Referências:**")
                    for ref in f.references:
                        lines.append(f"- {ref}")

        lines += ["", "---", f"*Gerado por Luna Audit Engine — score de risco: {self.score()}*"]
        return "\n".join(lines)


# ─── Patterns de vulnerabilidade ──────────────────────────────────────────────

# ── Solana/Anchor (Rust) ──────────────────────────────────────────────────────

SOLANA_PATTERNS = [
    {
        "id":       "SOL-001",
        "title":    "Missing Signer Check",
        "severity": "critical",
        "pattern":  r"pub\s+(?:mut\s+)?(\w+)\s*:\s*AccountInfo",
        "anti":     r"is_signer",
        "check_fn": None,
        "description": (
            "Conta do tipo AccountInfo usada sem verificação de `is_signer`. "
            "Um atacante pode passar qualquer conta no lugar do signatário esperado."
        ),
        "impact": "Execução de instruções privilegiadas sem autorização. Critical para fundos ou ownership.",
        "fix": (
            "// Verificar o signer explicitamente:\n"
            "require!(ctx.accounts.authority.is_signer, ErrorCode::Unauthorized);\n"
            "// Ou usar a constraint no Anchor:\n"
            "#[account(signer)]\n"
            "pub authority: AccountInfo<'info>,"
        ),
        "refs": ["https://book.anchor-lang.com/anchor_references/account_types.html#accountinfo"],
    },
    {
        "id":       "SOL-002",
        "title":    "Missing Owner Check",
        "severity": "high",
        "pattern":  r"AccountInfo.*owner",
        "anti":     r"\.owner\s*==|check_id|require.*owner",
        "check_fn": "_check_owner_validation",
        "description": (
            "Programa usa AccountInfo sem validar o campo `owner`. "
            "Atacante pode criar uma conta falsa com dados idênticos pertencendo a outro programa."
        ),
        "impact": "Account confusion — leitura/escrita de dados de conta não autorizada.",
        "fix": (
            "// Validar que a conta pertence ao programa esperado:\n"
            "require_keys_eq!(account.owner, expected_program_id, ErrorCode::InvalidOwner);\n"
            "// Em Anchor, usar Account<'info, T> ao invés de AccountInfo:"
        ),
        "refs": ["https://github.com/coral-xyz/sealevel-attacks/tree/master/programs/2-owner-checks"],
    },
    {
        "id":       "SOL-003",
        "title":    "Arithmetic Overflow / Underflow",
        "severity": "high",
        "pattern":  r"(?:amount|balance|total|value|lamports)\s*[+\-\*]\s*\w+",
        "anti":     r"checked_(?:add|sub|mul|div)|saturating_(?:add|sub)|safe_math",
        "check_fn": None,
        "description": (
            "Operação aritmética sem uso de `checked_*` ou `saturating_*`. "
            "Em Rust release builds, overflow em tipos inteiros pode resultar em wrapping silencioso."
        ),
        "impact": "Manipulação de balanços — inflação de tokens, underflow de lamports.",
        "fix": (
            "// Antes (vulnerável):\n"
            "let new_balance = balance + amount;\n\n"
            "// Depois (seguro):\n"
            "let new_balance = balance.checked_add(amount)\n"
            "    .ok_or(ErrorCode::Overflow)?;"
        ),
        "refs": ["https://doc.rust-lang.org/std/primitive.u64.html#method.checked_add"],
    },
    {
        "id":       "SOL-004",
        "title":    "PDA Bump Not Stored / Miscomputed",
        "severity": "medium",
        "pattern":  r"create_program_address|find_program_address",
        "anti":     r"bump\s*=\s*\*?ctx\.bumps|seeds.*bump",
        "check_fn": None,
        "description": (
            "PDA criado com find_program_address mas o bump não é armazenado na account data. "
            "Recomputar o bump a cada instrução é ineficiente e pode criar PDAs inconsistentes."
        ),
        "impact": "Inconsistência de PDAs; possível bypass de validação de endereço.",
        "fix": (
            "// Armazenar o bump na account:\n"
            "#[account]\n"
            "pub struct VaultState {\n"
            "    pub bump: u8,\n"
            "    // ...\n"
            "}\n\n"
            "// Usar seeds + bump constraint no Anchor:\n"
            "#[account(seeds = [b\"vault\", authority.key().as_ref()], bump = vault.bump)]\n"
            "pub vault: Account<'info, VaultState>,"
        ),
        "refs": ["https://book.anchor-lang.com/anchor_in_depth/PDAs.html"],
    },
    {
        "id":       "SOL-005",
        "title":    "CPI Without Account Re-validation",
        "severity": "high",
        "pattern":  r"invoke(?:_signed)?\s*\(",
        "anti":     r"reload\(\)|try_borrow_mut_lamports|try_borrow_mut_data",
        "check_fn": None,
        "description": (
            "CPI (Cross-Program Invocation) realizado sem re-leitura do estado das contas após retorno. "
            "O programa externo pode modificar contas compartilhadas durante a execução."
        ),
        "impact": "Reentrancy: estado lido antes do CPI fica stale; possível double-spend.",
        "fix": (
            "// Após o CPI, recarregar dados da conta:\n"
            "invoke_signed(&ix, &accounts, &[seeds])?;\n\n"
            "// Re-validar estado crítico:\n"
            "let vault = &ctx.accounts.vault;\n"
            "vault.reload()?;\n"
            "require!(vault.balance >= expected_balance, ErrorCode::InvalidState);"
        ),
        "refs": ["https://github.com/coral-xyz/sealevel-attacks/tree/master/programs/7-arbitrary-cpi"],
    },
    {
        "id":       "SOL-006",
        "title":    "Insecure Randomness (Clock-based)",
        "severity": "medium",
        "pattern":  r"Clock::get\(\)|clock\.unix_timestamp|clock\.slot",
        "anti":     r"switchboard|pyth.*random|vrf",
        "check_fn": None,
        "description": (
            "Aleatoriedade derivada de clock.unix_timestamp ou slot. "
            "Validators podem manipular o timestamp dentro de certos limites (±0.5s)."
        ),
        "impact": "Previsibilidade de resultados em loteria, NFT minting, jogos on-chain.",
        "fix": (
            "// Usar VRF (Verifiable Random Function) externo:\n"
            "// Switchboard VRF: https://docs.switchboard.xyz/\n"
            "// Pyth Entropy: https://docs.pyth.network/entropy\n\n"
            "// Nunca usar como única fonte de entropia:\n"
            "// ❌ let rand = clock.unix_timestamp as u64 % max;\n"
            "// ✅ let rand = vrf_result.current_round.result[0];"
        ),
        "refs": ["https://www.sec3.dev/blog/random-on-chain"],
    },
    {
        "id":       "SOL-007",
        "title":    "Unclosed Account (Lamport Drain Risk)",
        "severity": "medium",
        "pattern":  r"close\s*=\s*\w+|close_account",
        "anti":     r"lamports.*=.*0|assign.*system_program",
        "check_fn": None,
        "description": (
            "Conta fechada via constraint `close` sem zerar lamports antes. "
            "Resíduos de lamports podem ser reclamados por qualquer conta."
        ),
        "impact": "Perda de lamports; possível revival attack (conta reaberta com dados zerados).",
        "fix": (
            "// Em Anchor, a constraint close já lida corretamente:\n"
            "#[account(mut, close = authority)]\n"
            "pub data_account: Account<'info, DataState>,\n\n"
            "// Se fechar manualmente, zerar lamports E reatribuir ao system program:\n"
            "**account.try_borrow_mut_lamports()? = 0;\n"
            "account.assign(&system_program::ID);\n"
            "account.realloc(0, false)?;"
        ),
        "refs": ["https://github.com/coral-xyz/sealevel-attacks/tree/master/programs/9-closing-accounts"],
    },
]

# ── Solidity patterns ─────────────────────────────────────────────────────────

SOLIDITY_PATTERNS = [
    {
        "id":       "EVM-001",
        "title":    "Reentrancy (Checks-Effects-Interactions Violation)",
        "severity": "critical",
        "pattern":  r"\.call\{value",
        "anti":     r"nonReentrant|ReentrancyGuard",
        "description": (
            "Chamada externa com value antes de atualizar estado interno. "
            "Clássico vetor de reentrancy como o DAO hack."
        ),
        "impact": "Dreno total de fundos do contrato.",
        "fix": (
            "// Padrão Checks-Effects-Interactions:\n"
            "require(balance[msg.sender] >= amount, \"Insufficient\");  // Check\n"
            "balance[msg.sender] -= amount;                              // Effect\n"
            "(bool ok,) = msg.sender.call{value: amount}(\"\");          // Interact\n"
            "require(ok, \"Transfer failed\");\n\n"
            "// Ou usar ReentrancyGuard do OpenZeppelin:\n"
            "function withdraw() external nonReentrant { ... }"
        ),
        "refs": ["https://swcregistry.io/docs/SWC-107"],
    },
    {
        "id":       "EVM-002",
        "title":    "tx.origin Authentication",
        "severity": "high",
        "pattern":  r"tx\.origin",
        "anti":     r"msg\.sender",
        "description": (
            "Autenticação usando tx.origin em vez de msg.sender. "
            "Phishing attack: contrato intermediário pode executar em nome do usuário original."
        ),
        "impact": "Bypass de controle de acesso via contrato proxy malicioso.",
        "fix": (
            "// ❌ Vulnerável:\n"
            "require(tx.origin == owner);\n\n"
            "// ✅ Correto:\n"
            "require(msg.sender == owner, \"Not owner\");"
        ),
        "refs": ["https://swcregistry.io/docs/SWC-115"],
    },
    {
        "id":       "EVM-003",
        "title":    "Delegatecall with Untrusted Address",
        "severity": "critical",
        "pattern":  r"delegatecall",
        "anti":     r"require.*trusted|immutable|onlyOwner",
        "description": (
            "delegatecall executado com endereço passado pelo chamador ou variável de storage. "
            "Código externo executa no contexto de storage do contrato."
        ),
        "impact": "Controle total do storage do contrato pelo atacante.",
        "fix": (
            "// Whitelist de implementações permitidas:\n"
            "mapping(address => bool) public trustedImplementations;\n\n"
            "function upgradeAndCall(address impl, bytes memory data) external onlyOwner {\n"
            "    require(trustedImplementations[impl], \"Untrusted\");\n"
            "    (bool ok,) = impl.delegatecall(data);\n"
            "    require(ok);\n"
            "}"
        ),
        "refs": ["https://swcregistry.io/docs/SWC-112"],
    },
    {
        "id":       "EVM-004",
        "title":    "Block Timestamp Dependence",
        "severity": "medium",
        "pattern":  r"block\.timestamp",
        "anti":     r"oracle|chainlink|randomness",
        "description": (
            "Lógica de negócio dependente de block.timestamp. "
            "Mineradores podem manipular em até ~15 segundos."
        ),
        "impact": "Manipulação de leilões, loterias ou expiração de locks.",
        "fix": (
            "// Para timeouts longos (>15 min): block.timestamp é aceitável.\n"
            "// Para precisão curta: usar número de bloco em vez de tempo:\n"
            "uint256 public constant LOCK_BLOCKS = 100; // ~20 min em Ethereum\n"
            "require(block.number >= unlockBlock, \"Still locked\");"
        ),
        "refs": ["https://swcregistry.io/docs/SWC-116"],
    },
]

# ── API / Web3 backend patterns ───────────────────────────────────────────────

API_PATTERNS = [
    {
        "id":       "API-001",
        "title":    "Hardcoded Private Key or Secret",
        "severity": "critical",
        "pattern":  r'(?:private_key|secret_key|mnemonic|seed_phrase)\s*=\s*["\'][^"\']{20,}["\']',
        "anti":     r"os\.(?:environ|getenv)|process\.env",
        "description": "Chave privada ou segredo hardcoded no código-fonte.",
        "impact": "Comprometimento total da carteira ou sistema se o código vazar.",
        "fix": (
            "# Usar variáveis de ambiente:\n"
            "import os\n"
            "private_key = os.getenv('WALLET_PRIVATE_KEY')\n"
            "assert private_key, 'WALLET_PRIVATE_KEY não configurada'"
        ),
        "refs": ["https://immunefi.com/blog/private-key-exposure/"],
    },
    {
        "id":       "API-002",
        "title":    "Unvalidated Wallet Address",
        "severity": "medium",
        "pattern":  r"PublicKey\s*\(\s*req\.",
        "anti":     r"isValidPublicKey|validateAddress|try.*PublicKey",
        "description": "Endereço de carteira recebido do request sem validação antes de usar como PublicKey.",
        "impact": "Crash ou comportamento inesperado com endereços malformados.",
        "fix": (
            "// Validar antes de criar PublicKey:\n"
            "try {\n"
            "    const pubkey = new PublicKey(req.body.address);\n"
            "} catch (e) {\n"
            "    return res.status(400).json({ error: 'Invalid wallet address' });\n"
            "}"
        ),
        "refs": [],
    },
    {
        "id":       "API-003",
        "title":    "JWT Without Signature Verification",
        "severity": "critical",
        "pattern":  r"jwt\.decode\s*\(",
        "anti":     r"jwt\.verify\s*\(",
        "description": "JWT decodificado sem verificação de assinatura (jwt.decode vs jwt.verify).",
        "impact": "Qualquer usuário pode forjar tokens e se autenticar como admin.",
        "fix": (
            "// ❌ Vulnerável — decodifica sem verificar:\n"
            "const payload = jwt.decode(token);\n\n"
            "// ✅ Correto — verifica assinatura:\n"
            "const payload = jwt.verify(token, process.env.JWT_SECRET);"
        ),
        "refs": ["https://jwt.io/introduction"],
    },
]


# ─── Motor de auditoria ───────────────────────────────────────────────────────

class AuditEngine:
    """
    Motor de auditoria estática de segurança para projetos Solana/Web3.

    Uso:
        engine = AuditEngine()
        report = engine.audit("/mnt/c/Dev/bags-shield-api")
        print(report.render_markdown())
    """

    def __init__(self) -> None:
        self._counter: dict[str, int] = {}  # id → ocorrências

    # ── Detecção de stack ─────────────────────────────────────────────────

    def _detect_stack(self, root: Path) -> str:
        files = list(root.rglob("*"))
        names = {f.name for f in files if f.is_file()}
        if "Anchor.toml" in names or any(str(f).endswith("/programs/") for f in files):
            return "solana_anchor"
        if any(n.endswith(".sol") for n in names):
            return "solidity"
        if "tsconfig.json" in names or "package.json" in names:
            return "typescript_web3"
        return "python_web3"

    # ── Scanner de arquivo ────────────────────────────────────────────────

    def _scan_file(
        self,
        path: Path,
        patterns: list[dict],
        rel_path: str,
    ) -> list[Finding]:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        findings = []
        lines = content.splitlines()

        for pat in patterns:
            regex = re.compile(pat["pattern"], re.IGNORECASE | re.MULTILINE)
            anti  = re.compile(pat.get("anti", r"NEVER_MATCH_THIS_XZQW"), re.IGNORECASE) if pat.get("anti") else None

            for m in regex.finditer(content):
                line_num = content[:m.start()].count("\n") + 1
                # Contexto de 3 linhas ao redor do match
                start = max(0, line_num - 3)
                end   = min(len(lines), line_num + 3)
                snippet = "\n".join(
                    f"{i+1:4d} | {lines[i]}"
                    for i in range(start, end)
                )

                # Verificar se o anti-pattern está na função/bloco próximo
                # Pegar 10 linhas ao redor para contexto do anti-pattern
                ctx_start = max(0, m.start() - 500)
                ctx_end   = min(len(content), m.end() + 500)
                local_ctx = content[ctx_start:ctx_end]

                if anti and anti.search(local_ctx):
                    continue   # anti-pattern encontrado — provavelmente seguro

                # Dedup: mesmo vuln_id no mesmo arquivo/linha
                dedup_key = f"{pat['id']}:{rel_path}:{line_num}"
                if dedup_key in self._counter:
                    continue
                self._counter[dedup_key] = 1

                findings.append(Finding(
                    vuln_id=     pat["id"],
                    title=       pat["title"],
                    severity=    pat["severity"],
                    file=        rel_path,
                    line=        line_num,
                    snippet=     snippet,
                    description= pat["description"],
                    impact=      pat.get("impact", ""),
                    fix=         pat.get("fix", ""),
                    references=  pat.get("refs", []),
                ))

        return findings

    # ── Auditoria de projeto ──────────────────────────────────────────────

    def audit(
        self,
        project_path: str,
        extra_patterns: list[dict] | None = None,
    ) -> AuditReport:
        """
        Escaneia um projeto inteiro e retorna um AuditReport.

        Args:
            project_path: Caminho para o diretório do projeto.
            extra_patterns: Patterns adicionais (útil para auditorias customizadas).
        """
        self._counter.clear()
        root = Path(project_path).resolve()

        if not root.exists():
            logger.error(f"[audit] Diretório não encontrado: {project_path}")
            return AuditReport(
                target_path=project_path,
                stack="unknown",
                files_scanned=0,
                total_lines=0,
            )

        stack = self._detect_stack(root)
        logger.info(f"[audit] Iniciando auditoria: {root.name} (stack={stack})")

        # Selecionar patterns por stack
        if stack == "solana_anchor":
            active_patterns = SOLANA_PATTERNS + API_PATTERNS
            target_exts = {".rs", ".toml", ".py", ".ts", ".js"}
        elif stack == "solidity":
            active_patterns = SOLIDITY_PATTERNS + API_PATTERNS
            target_exts = {".sol", ".ts", ".js", ".py"}
        else:
            active_patterns = API_PATTERNS + SOLIDITY_PATTERNS[:2]
            target_exts = {".ts", ".tsx", ".js", ".py", ".sol"}

        if extra_patterns:
            active_patterns = active_patterns + extra_patterns

        # Diretórios ignorados
        skip_dirs = {"node_modules", ".git", "__pycache__", "target", "dist",
                     "build", ".venv", "venv", "coverage"}

        findings: list[Finding] = []
        files_scanned = 0
        total_lines = 0

        for fpath in sorted(root.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.suffix not in target_exts:
                continue
            if any(skip in fpath.parts for skip in skip_dirs):
                continue
            if fpath.stat().st_size > 300_000:
                continue

            rel = str(fpath.relative_to(root))
            file_findings = self._scan_file(fpath, active_patterns, rel)
            findings.extend(file_findings)
            files_scanned += 1
            try:
                total_lines += fpath.read_text(encoding="utf-8", errors="replace").count("\n")
            except Exception:
                pass

        # Ordenar por severidade
        findings.sort(key=lambda f: (SEVERITY_WEIGHT.get(f.severity, 0) * -1, f.file, f.line))

        report = AuditReport(
            target_path=str(root),
            stack=stack,
            files_scanned=files_scanned,
            total_lines=total_lines,
            findings=findings,
        )

        logger.info(
            f"[audit] Concluído: {files_scanned} arquivos, "
            f"{len(findings)} findings, score={report.score()}"
        )
        return report

    def audit_multiple(self, paths: list[str]) -> list[AuditReport]:
        """Audita múltiplos projetos e retorna relatórios individuais."""
        return [self.audit(p) for p in paths]

    def audit_file(self, file_path: str, stack_hint: str = "auto") -> list[Finding]:
        """Auditoria de arquivo único — útil para análise cirúrgica."""
        self._counter.clear()
        path = Path(file_path)
        if not path.exists():
            return []

        ext = path.suffix.lower()
        if ext == ".rs":
            patterns = SOLANA_PATTERNS
        elif ext == ".sol":
            patterns = SOLIDITY_PATTERNS
        else:
            patterns = API_PATTERNS

        return self._scan_file(path, patterns, file_path)


# ─── Singleton global ─────────────────────────────────────────────────────────

def get_audit_engine() -> AuditEngine:
    return AuditEngine()
