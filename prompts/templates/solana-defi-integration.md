# Template: Solana DeFi Integrations

Use ao integrar com Jupiter, Raydium, Orca, Jito, Squads, Metaplex.

## Jupiter (swap aggregator) - v6 API
```typescript
import axios from "axios";

const quote = await axios.get("https://quote-api.jup.ag/v6/quote", {
  params: {
    inputMint: "So11111111111111111111111111111111111111112",
    outputMint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    amount: 1_000_000_000,  // 1 SOL em lamports
    slippageBps: 50,
  },
});

const { swapTransaction } = (await axios.post("https://quote-api.jup.ag/v6/swap", {
  quoteResponse: quote.data,
  userPublicKey: wallet.publicKey.toBase58(),
  wrapAndUnwrapSol: true,
})).data;

const txBuf = Buffer.from(swapTransaction, "base64");
const tx = VersionedTransaction.deserialize(txBuf);
tx.sign([wallet]);
const sig = await connection.sendTransaction(tx);
```

## Raydium AMM V4 / CLMM
- SDK: `@raydium-io/raydium-sdk-v2`
- Pools: fetch via `fetchPoolInfos()` por mint pair
- CLMM: atento a tick ranges e rebalance

## Jito (MEV/bundles)
```typescript
import { searcherClient } from "jito-ts/dist/sdk/block-engine/searcher";
const client = searcherClient("frankfurt.mainnet.block-engine.jito.wtf");
await client.sendBundle(new Bundle([tx1, tx2, tipTx], 5));
```
Usar para: protecao contra sandwich, atomic multi-tx, tip para inclusao rapida.

## Metaplex (NFT, Core)
- **Token Metadata** (legacy): `@metaplex-foundation/mpl-token-metadata`
- **Core** (novo, recomendado 2025): `@metaplex-foundation/mpl-core`
- Umi framework: `@metaplex-foundation/umi-bundle-defaults`

## Squads Multisig
```typescript
import * as multisig from "@sqds/multisig";
const createIx = multisig.instructions.multisigCreate({
  createKey: PublicKey.unique(),
  creator: wallet.publicKey,
  multisigPda,
  configAuthority: null,
  threshold: 2,
  members: [...],
  timeLock: 0,
});
```

## Helius (RPC + Enhanced + Webhooks + LaserStream)
- Enhanced Transactions: `getParsedTransactionHistory()` com decode automatico
- Webhooks: filtro por account address, tipo de tx
- DAS (Digital Asset Standard): `searchAssets()` substitui metaplex fetch

## Security checklist para integracoes
- [ ] Sempre validar retorno do quote ANTES de assinar
- [ ] Slippage max configurado pelo usuario
- [ ] Priority fee adaptativo (usar getRecentPrioritizationFees)
- [ ] Simular tx antes de enviar (`simulateTransaction`)
- [ ] Compute budget ixs (ComputeBudgetProgram.setComputeUnitLimit)
- [ ] Versioned transactions (V0) com ALT para ixs complexas
- [ ] Retry com exponential backoff + novo blockhash

## Regras de entrega
1. Usar SDKs oficiais, nunca reimplementar serializacao de accounts
2. Simular em devnet antes de mainnet
3. Logs estruturados de cada etapa (quote, sign, send, confirm)
4. Error handling: distinguir "user rejected", "insufficient funds", "slippage"
5. Testar com valores pequenos ($1) antes de volume maior