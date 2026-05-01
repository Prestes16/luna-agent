# Template: Report Immunefi (Web3/Solana)

## Formato obrigatorio

```markdown
# [TITULO CURTO E IMPACTANTE] - Severity: [Critical/High/Medium/Low]

## Summary
[1-2 paragrafos: o que e, onde esta, qual o impacto direto em fundos/state]

## Vulnerability Details
- **Target Program**: `<program_id>`
- **Vulnerable Instruction**: `instruction_name`
- **File**: `programs/xxx/src/yyy.rs:LINE`
- **Vulnerability Class**: [missing_signer / arithmetic_overflow / cpi_reentrancy / ...]
- **CWE**: CWE-XXX

## Impact
[Quantificar: quanto pode ser drenado, quantos usuarios afetados, tempo de recovery]
- Funds at risk: `$X` (baseado em TVL atual `$Y`)
- Accounts affected: `N`
- Reversibility: [recoverable / irreversible]

## Root Cause
[Codigo exato com highlight da linha, explicacao tecnica do porque e vulneravel]

\`\`\`rust
// programs/xxx/src/yyy.rs
pub fn vulnerable_ix(ctx: Context<VulnerableCtx>, amount: u64) -> Result<()> {
    // LINHA VULNERAVEL - missing signer check
    let user = &ctx.accounts.user;
    token::transfer(..., amount)?;   // atacante pode ser qualquer um
    Ok(())
}
\`\`\`

## Proof of Concept

### Setup
```bash
solana-test-validator --reset
anchor build && anchor deploy
```

### Attack
\`\`\`typescript
// poc/exploit.ts
const attacker = Keypair.generate();
await program.methods.vulnerableIx(new BN(1_000_000))
  .accounts({ user: victim.publicKey, attacker: attacker.publicKey })
  .signers([attacker])
  .rpc();
\`\`\`

### Expected Output
```
Before: victim=1000 SOL, attacker=0 SOL
After:  victim=0 SOL,    attacker=1000 SOL
```

## Recommended Fix
\`\`\`rust
#[account(mut, constraint = user.key() == expected_authority.key())]
pub user: Signer<'info>,   // <-- exige signature
\`\`\`

Ou validacao explicita:
\`\`\`rust
require_keys_eq!(ctx.accounts.user.key(), ctx.accounts.authority.key());
\`\`\`

## References
- SolSec docs: [link]
- Sealevel attacks: [link]
- Similar CVE: [link]
```

## Regras Immunefi
- Severity baseada em Immunefi Vulnerability Severity Classification System
- PoC reproduzivel em localnet OU devnet (nunca mainnet sem autorizacao)
- Nao publicar o bug ate pagamento + disclosure liberado
- Responder a triager em ate 24h

## Checklist antes de submeter
- [ ] Scope: programa esta na lista oficial do bounty?
- [ ] Severity alinha com a tabela Immunefi?
- [ ] PoC roda em ambiente limpo?
- [ ] Codigo vulneravel cita arquivo:linha exatos?
- [ ] Mitigation proposta compila e mantem funcionalidade?
- [ ] Impact quantificado com numeros (TVL, usuarios)?