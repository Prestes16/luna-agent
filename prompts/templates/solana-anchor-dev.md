# Template: Solana/Anchor Development

Use quando o usuario pedir "programa Solana", "contrato Anchor", "token", "SPL", "smart contract Solana".

## Stack
- Rust 1.75+
- Anchor 0.30+ (preferir stable 0.30.1 em 2025)
- solana-cli 1.18+
- Node 18+ para testes TS

## Scaffold oficial
```bash
anchor init meu-programa
cd meu-programa
anchor build
anchor test
```

## Estrutura canonica
```
meu-programa/
  Anchor.toml
  Cargo.toml
  programs/
    meu-programa/
      Cargo.toml
      src/
        lib.rs              # entry, #[program]
        instructions/       # uma ix por arquivo
          initialize.rs
          deposit.rs
          withdraw.rs
        state/              # contas do programa
          vault.rs
          user_account.rs
        error.rs            # #[error_code]
        constants.rs        # seeds, fees, limits
  tests/
    meu-programa.ts         # mocha + anchor TS client
  migrations/
    deploy.ts
```

## Padrao de instrucao (use sempre)
```rust
// programs/.../src/instructions/deposit.rs
use anchor_lang::prelude::*;
use anchor_spl::token::{Token, TokenAccount, Transfer, transfer};

#[derive(Accounts)]
#[instruction(amount: u64)]
pub struct Deposit<'info> {
    #[account(mut, has_one = authority)]
    pub vault: Account<'info, Vault>,

    #[account(
        mut,
        associated_token::mint = vault.mint,
        associated_token::authority = authority,
    )]
    pub user_token: Account<'info, TokenAccount>,

    #[account(
        mut,
        associated_token::mint = vault.mint,
        associated_token::authority = vault,
    )]
    pub vault_token: Account<'info, TokenAccount>,

    pub authority: Signer<'info>,
    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<Deposit>, amount: u64) -> Result<()> {
    require!(amount > 0, ErrorCode::InvalidAmount);
    require!(amount <= ctx.accounts.user_token.amount, ErrorCode::InsufficientBalance);

    transfer(
        CpiContext::new(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.user_token.to_account_info(),
                to: ctx.accounts.vault_token.to_account_info(),
                authority: ctx.accounts.authority.to_account_info(),
            },
        ),
        amount,
    )?;

    ctx.accounts.vault.total_deposited = ctx.accounts.vault.total_deposited
        .checked_add(amount)
        .ok_or(ErrorCode::MathOverflow)?;

    emit!(DepositEvent { user: ctx.accounts.authority.key(), amount });
    Ok(())
}
```

## PDA canonico
```rust
pub const VAULT_SEED: &[u8] = b"vault";

#[account(
    init,
    payer = authority,
    space = 8 + Vault::INIT_SPACE,
    seeds = [VAULT_SEED, mint.key().as_ref()],
    bump,
)]
pub vault: Account<'info, Vault>,
```

## Error codes
```rust
#[error_code]
pub enum ErrorCode {
    #[msg("Invalid amount")]
    InvalidAmount,
    #[msg("Insufficient balance")]
    InsufficientBalance,
    #[msg("Math overflow")]
    MathOverflow,
}
```

## Testes (TS) com happy + attack paths
```typescript
describe("vault", () => {
  it("deposit happy path", async () => { /* ... */ });
  it("fails on zero amount", async () => {
    await assert.rejects(
      program.methods.deposit(new BN(0)).accounts({...}).rpc(),
      /InvalidAmount/
    );
  });
  it("fails when attacker signs for victim", async () => {
    // tentar drenar vault de outra authority
  });
});
```

## Regras de entrega
1. Scaffold com `anchor init` - nao escrever Anchor.toml manualmente
2. Toda instrucao tem happy path E pelo menos 2 attack tests
3. Todo PDA tem seed constante em constants.rs
4. Toda aritmetica usa checked_*
5. anchor build e anchor test passam antes de entregar
6. Gerar IDL limpo e rodar `solana_parse_idl` para red flags

## Anti-padroes
- AccountInfo<'info> quando Account<T> resolve
- Sem has_one em contas relacionadas
- Seeds dinamicos dependentes de input sem validacao
- close= sem zeroizacao
- CPI para programa passado como input sem whitelist