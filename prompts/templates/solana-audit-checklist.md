# Checklist: Solana/Anchor Audit

## Pipeline Luna recomendado
1. `solana_parse_idl(idl.json)` - red flags automaticos
2. `solana_rust_scan(project_path)` - static Rust refinado
3. `audit_toolkit.run()` (hunter) - Soteria + Anchor-Linter + Trident
4. `solana_cpi_graph(project_path)` - mapear CPIs
5. Para cada finding High/Critical: `poc_generator` gera Rust + TS PoC

## Classes de vulnerabilidade (revisar todas)

### A. Ownership & signer
- [ ] Toda conta modificada tem `mut`?
- [ ] Toda autoridade tem `Signer<'info>` ou constraint de signer?
- [ ] `has_one` em contas relacionadas (ex: vault has_one = authority)?
- [ ] Owner check explicito para AccountInfo/UncheckedAccount?
- [ ] Programa alvo de CPI validado (Program<'info, Token> vs AccountInfo)?

### B. Aritmetica
- [ ] checked_add / checked_sub / checked_mul / checked_div em TUDO?
- [ ] Cast `as u64` de i64/u128 validado antes?
- [ ] Divisao por zero tratada?
- [ ] Precision loss em operacoes com decimals?

### C. PDA
- [ ] Seeds canonicos (constantes em constants.rs)?
- [ ] Bump armazenado ou validado com canonical_bump?
- [ ] PDA collision: seeds unicos por usuario/contexto?
- [ ] Re-inicializacao bloqueada (init vs init_if_needed)?

### D. Account closure
- [ ] close= com zeroizacao (manual_close + zero-copy)?
- [ ] Lamports drenados antes do close?
- [ ] Sem revival: attacker nao pode re-inicializar conta fechada?

### E. CPI
- [ ] CPI para programa whitelist (nunca programa arbitrario)?
- [ ] PDA signer seeds validos (bump canonico)?
- [ ] Reentrancy: nao chamar de volta para mesmo programa com state inconsistente?
- [ ] Arbitrary CPI: programa de destino validado?

### F. Token-2022 (cuidado redobrado)
- [ ] Transfer hooks: atacante pode injetar hook malicioso?
- [ ] Permanent Delegate: transferencias unilaterais possiveis?
- [ ] Confidential Transfers: estado oculto confiavel?
- [ ] Transfer Fee: calculos de amount consideram fee?

### G. Sysvar / oracle
- [ ] Clock manipulation: validator custom pode mentir?
- [ ] Pyth/Switchboard: staleness check (slot/timestamp)?
- [ ] Oracle price confidence validado?

### H. Flash loan / MEV
- [ ] Preco/state pode ser manipulado em uma tx com flash loan?
- [ ] Slippage protection nas trocas?
- [ ] Sandwich: ordem de processamento importa?

### I. Denial of service
- [ ] Loops com tamanho controlado pelo input?
- [ ] Realloc dinamico com limite?
- [ ] Stack/heap overflow em serializacao?

## Severity rubric
- **Critical**: drenar fundos de qualquer usuario, bypass completo de auth
- **High**: roubar fundos em condicoes especificas, escalation de privilegios
- **Medium**: DoS, info leak, race condition com pre-req improvavel
- **Low**: best practice violations sem impacto direto

## Entregaveis do audit
1. Lista de findings (arquivo:linha, classe, severity)
2. PoC Rust + TS para cada High/Critical
3. Suggested fix com codigo
4. Relatorio no formato bounty-report-immunefi.md