# Template: BUILD_LAUNCHPAD — Plataformas de launchpad Solana (PC + Mobile)

Template dedicado a construir launchpads e clientes de launchpad na Solana.
Cobre os dois modos de entrega:
- **PC / Web** (Next.js + shadcn + wallet-adapter-react)
- **Mobile** (Expo + React Native + Mobile Wallet Adapter)

Escolha de modo: se o pedido mencionar "mobile", "app", "iOS/Android" → Mobile.
Se mencionar "site", "web", "dashboard", "plataforma" → PC/Web.
Se não especificar → perguntar ao usuário OU construir os dois (monorepo).

---

## O que é um launchpad (para não errar escopo)

Um launchpad é uma plataforma que executa três coisas:

1. **Criação de token** — mint SPL + metadata (Metaplex Token Metadata v2 ou Token-2022 com metadata extension)
2. **Curva de liquidez / bonding curve** — preço sobe conforme compras (Pump.fun, Raydium LaunchLab, Meteora DBC)
3. **Graduação / Listagem** — quando atinge market cap alvo, migra para AMM (Raydium CPMM, Meteora DAMM v2, Orca Whirlpools)

O cliente (app/site) faz 3 jornadas:
- **Launch** — criar um token novo
- **Trade** — comprar/vender tokens em curva ou AMM
- **Explore** — ver trending, últimos lançamentos, detalhes de token

---

## APIs e integrações dedicadas (use as oficiais)

### Pump.fun
- **PumpPortal** `https://pumpportal.fun/api` — trading API não-oficial mas estável
  - Endpoints: `/trade-local` (constrói tx local), `/trade` (executa remoto)
  - Payload: `action` (buy/sell), `mint`, `amount`, `denominatedInSol`, `slippage`, `priorityFee`, `pool` (pump ou pump-amm)
- **Pump.fun program** `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` — instruções: `create`, `buy`, `sell`
- **Dados:** Bitquery ou Solana Tracker API para candles/holders/trades históricos

### Raydium LaunchLab (bonding curve oficial Raydium)
- **SDK:** `@raydium-io/raydium-sdk-v2` com `LaunchLab` module
- **Program ID:** `LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj`
- Fluxo: `create` → `buy/sell` na curva → migração automática para CPMM em ~85 SOL

### Meteora Dynamic Bonding Curve (DBC)
- **SDK:** `@meteora-ag/dynamic-bonding-curve-sdk`
- **Program ID:** `dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN`
- DBC é a curva; após graduação, migra para DAMM v2 (`@meteora-ag/cp-amm-sdk`)
- Único que permite configurar bonding curve customizado (preço inicial, reserva, fees)

### Jupiter Studio / Jupiter Lend / Jupiter Aggregator
- **`@jup-ag/api`** — para quotes e swaps multi-rota (já após graduação do token)
- Útil para roteamento ótimo quando o token já está em pool

### Moonshot / Dexscreener
- **Moonshot SDK:** `@wen-moon-ser/moonshot-sdk` — criar + comprar/vender
- **Dexscreener API:** `https://api.dexscreener.com/latest/dex/tokens/{mint}` — preço, liquidez, volume
- Moonshot permite compra via cartão (Stripe on-ramp) — diferencial para mobile

### Metaplex (mint e metadata)
- **`@metaplex-foundation/mpl-token-metadata`** + **`@metaplex-foundation/umi`**
- Para Token-2022 com metadata extension: `@solana/spl-token` v0.4+ direto

### Helius (dados on-chain enriquecidos)
- **DAS API** — listar todos os tokens de um owner com metadata + preço
- **Enhanced WebSockets** — stream de compras/vendas em tempo real de um mint
- **Enhanced Transactions** — decode de instruções Pump/Raydium/Meteora sem parser manual

### Birdeye / DexScreener / Solana Tracker
- **Birdeye:** `https://public-api.birdeye.so` (candles OHLCV, holders, trades)
- **DexScreener:** dados gratuitos de pares e volume
- **Solana Tracker:** `https://data.solanatracker.io` — API focada em memecoins/launchpads

---

## Stack PC / Web — Next.js + shadcn

```bash
npx create-next-app@latest launchpad -- --app --ts --tailwind --eslint
cd launchpad
npx shadcn@latest init -d

# Wallet + Solana
npm install @solana/web3.js @solana/wallet-adapter-react \
  @solana/wallet-adapter-react-ui @solana/wallet-adapter-wallets \
  @solana/spl-token bs58 bn.js

# Launchpad SDKs (instalar só os que o projeto usar)
npm install @raydium-io/raydium-sdk-v2
npm install @meteora-ag/dynamic-bonding-curve-sdk @meteora-ag/cp-amm-sdk
npm install @metaplex-foundation/mpl-token-metadata @metaplex-foundation/umi \
  @metaplex-foundation/umi-bundle-defaults
npm install @jup-ag/api

# Dados e UI
npm install @tanstack/react-query zustand lightweight-charts \
  framer-motion lucide-react sonner
```

### Páginas obrigatórias (App Router)
```
app/
  page.tsx                    # landing + trending
  launch/page.tsx             # wizard de criação de token
  token/[mint]/page.tsx       # detalhe: chart + trade panel + holders + socials
  portfolio/page.tsx          # meus tokens criados + comprados
  explore/page.tsx            # filtros: graduating, new, top volume, top holders
  api/
    pump-portal/trade/route.ts      # proxy para PumpPortal (evita CORS + esconde keys)
    helius/das/route.ts             # proxy DAS
    birdeye/candles/route.ts        # proxy Birdeye
```

### Trade panel (componente central)
Deve sempre mostrar:
- Saldo SOL + saldo do token do usuário
- Input de amount (SOL ou token)
- Switch "buy / sell"
- Slippage ajustável (default 1%, modificável)
- Priority fee ajustável (slow/fast/turbo)
- Preview: amount out, preço impact, fee total
- Botão que abre modal de confirmação com todos os números
- Após confirmação: toast com link Solscan + refetch

---

## Stack Mobile — Expo + MWA (leia também `solana-mobile-defi.md`)

```bash
npx create-expo-app@latest launchpad-mobile -t
cd launchpad-mobile

# Core Solana + MWA (mesmo bloco do template solana-mobile-defi.md)
npx expo install @solana/web3.js \
  @solana-mobile/mobile-wallet-adapter-protocol \
  @solana-mobile/mobile-wallet-adapter-protocol-web3js \
  @solana-mobile/wallet-adapter-mobile \
  @solana/spl-token buffer react-native-get-random-values

# Launchpad SDKs (mesmos do PC — funcionam em RN com polyfills)
npm install @raydium-io/raydium-sdk-v2
npm install @meteora-ag/dynamic-bonding-curve-sdk
npm install @metaplex-foundation/mpl-token-metadata @metaplex-foundation/umi

# UI mobile-first
npx expo install @gorhom/bottom-sheet @shopify/flash-list \
  react-native-reanimated react-native-gesture-handler \
  react-native-svg expo-haptics expo-local-authentication \
  expo-secure-store expo-image-picker
npm install react-native-wagmi-charts   # candles nativos
```

### Telas obrigatórias (expo-router)
```
app/
  (tabs)/
    index.tsx          # Trending (scroll infinito com FlashList)
    explore.tsx        # Filtros + busca
    portfolio.tsx
    launch.tsx         # Wizard de criação (bottom sheets multi-step)
  token/[mint].tsx     # Detalhe com chart + trade bottom sheet
  _layout.tsx
```

### Trade flow mobile (bottom sheet de 3 snap points)
- Snap 25%: resumo rápido (preço, 24h, botões buy/sell)
- Snap 60%: input de valor + preview + slippage
- Snap 95%: confirmação detalhada + biometria → assina via MWA

---

## Wizard de criação de token (core do launchpad)

Passos padronizados (PC e mobile):

1. **Metadata**
   - Nome (máx 32 chars)
   - Symbol (máx 10 chars)
   - Descrição (máx 500 chars)
   - Imagem (upload → IPFS via NFT.Storage, Pinata ou Arweave)
   - Links: website, twitter, telegram, discord

2. **Economia**
   - Total supply (default 1_000_000_000)
   - Decimals (default 6 para memecoin, 9 para utility)
   - Escolha do launchpad:
     - Pump.fun (rápido, fee fixo, graduação ~85 SOL)
     - Raydium LaunchLab (mesma curva, migra para Raydium CPMM)
     - Meteora DBC (curva customizável, migra para DAMM v2)

3. **Curva (apenas se Meteora DBC)**
   - Preço inicial (SOL por token)
   - Reserva total
   - Fees (bps LP + bps criador)

4. **Preview e confirmação**
   - Custo total estimado (deploy + initial buy opcional)
   - Initial buy (criador compra X% no deploy — anti-sniper)
   - Botão assinar — PC: wallet adapter; Mobile: MWA + biometria

5. **Pós-deploy**
   - Mostrar mint address + link Solscan
   - Botão copiar contrato
   - Redirect para `token/[mint]`
   - Toast de sucesso + confete

---

## Exemplo — Compra em Pump.fun via PumpPortal

```typescript
// lib/pumpportal.ts
import { VersionedTransaction, Connection } from '@solana/web3.js'

export async function buildPumpBuy(opts: {
  publicKey: string
  mint: string
  amountSol: number
  slippage: number       // 1 = 1%
  priorityFee: number    // em SOL
}) {
  const r = await fetch('https://pumpportal.fun/api/trade-local', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      publicKey: opts.publicKey,
      action: 'buy',
      mint: opts.mint,
      amount: opts.amountSol,
      denominatedInSol: 'true',
      slippage: opts.slippage,
      priorityFee: opts.priorityFee,
      pool: 'pump',
    }),
  })
  if (!r.ok) throw new Error(`PumpPortal ${r.status}: ${await r.text()}`)
  const buf = new Uint8Array(await r.arrayBuffer())
  return VersionedTransaction.deserialize(buf)
}
```

PC assina com `wallet.signTransaction(tx)` + `connection.sendRawTransaction`.
Mobile assina com `signAndSend(tx, authToken)` via MWA.

---

## Exemplo — Deploy via Raydium LaunchLab

```typescript
import { Raydium, TxVersion } from '@raydium-io/raydium-sdk-v2'

const raydium = await Raydium.load({
  connection, owner: userPubkey, cluster: 'mainnet',
  disableFeatureCheck: true, blockhashCommitment: 'finalized',
})

const { execute } = await raydium.launchpad.createLaunchpad({
  programId: LAUNCHPAD_PROGRAM,
  mintA: newMintKeypair.publicKey,
  decimals: 6,
  name: 'Meu Token',
  symbol: 'MEU',
  uri: 'ipfs://...',   // metadata JSON
  supply: new BN('1000000000000000'),
  totalSellA: new BN('800000000000000'),
  totalFundRaisingB: new BN('85_000_000_000'),  // 85 SOL
  migrateType: 'cpmm',
  buyAmount: new BN('100_000_000'), // 0.1 SOL initial buy
  txVersion: TxVersion.V0,
})
const { txId } = await execute({ sendAndConfirm: true })
```

---

## Chart ao vivo (PC com lightweight-charts, mobile com wagmi-charts)

Fonte de velas (prioridade):
1. **Birdeye public API** — `GET /defi/history_price?address={mint}&type=1m&time_from=...`
2. **Solana Tracker** — `GET /price/{mint}` + candles
3. **Helius Enhanced WebSocket** + agregação client-side (último recurso)

Atualização ao vivo:
- WebSocket Helius subscrevendo trades do mint → atualiza última vela
- Refetch candles históricos a cada 1min via `useQuery` com `refetchInterval`

---

## Segurança crítica de launchpad

- **Anti-rug:** ao mostrar token, destacar se o criador revogou mint authority / freeze authority. Use `getMint` + checar `mintAuthority === null` e `freezeAuthority === null`
- **Top 10 holders %:** se top 10 detêm > 30%, mostrar aviso vermelho
- **Honeypot check:** simular `sell` de 0.001 SOL equivalente antes de deixar usuário comprar. Se `simulateTransaction` falhar no sell, marcar como potencial honeypot
- **Slippage máximo:** nunca aceitar slippage > 50% (usuário provavelmente não entende)
- **Priority fee razoável:** cap em 0.01 SOL para evitar drenar wallet por engano
- **Confirmação dupla em launch:** antes de criar token, mostrar modal com TODAS as informações e exigir digitação do symbol para confirmar
- **Rate limit em APIs:** PumpPortal e Birdeye têm limites — cachear via react-query com `staleTime: 10_000` mínimo
- **IPFS upload com retry:** usar fallback NFT.Storage → Pinata → Arweave
- **Validação de URI de metadata:** fetch e validar JSON antes de chamar `createLaunchpad`

---

## Anti-padrões de launchpad

- ❌ Criar token sem metadata válido (aparece como "Unknown Token" em wallets)
- ❌ Não mostrar bonding curve progress (% para graduar)
- ❌ Permitir trade sem mostrar taxa + impact
- ❌ Chart estático sem atualização ao vivo
- ❌ Não diferenciar tokens em curva vs graduados (rotas são diferentes)
- ❌ Usar RPC público em produção — rate limit mata o site
- ❌ Guardar seed phrase para "auto-buy" — inaceitável, sempre MWA ou wallet adapter
- ❌ Initial buy 100% do criador — é honeypot, alertar usuário
- ❌ Confiar em preço off-chain sem validar on-chain antes de assinar

---

## Checklist de entrega de launchpad

PC:
- [ ] Wallet adapter conectando Phantom + Solflare + Backpack
- [ ] Landing com tokens trending (auto-refresh)
- [ ] Página de detalhe com chart + trade panel funcional
- [ ] Wizard de criação com upload IPFS
- [ ] Ao menos 1 launchpad integrado end-to-end (Pump ou Raydium ou Meteora)
- [ ] Honeypot check + revogação de authorities visíveis no detalhe
- [ ] Slippage + priority fee ajustáveis
- [ ] Toast com Solscan após sucesso
- [ ] Build `npm run build` limpo

Mobile:
- [ ] MWA: connect + signAndSend em Pump/Raydium/Meteora
- [ ] Bottom sheet para trade (3 snap points)
- [ ] Wizard de criação com upload via `expo-image-picker`
- [ ] Chart com `react-native-wagmi-charts` + stream Helius
- [ ] Biometria antes de assinar
- [ ] FlashList para trending (scroll infinito)
- [ ] `npx expo start` limpo em device físico

Compartilhado:
- [ ] `.env.example` com: `HELIUS_API_KEY`, `BIRDEYE_API_KEY`, `NFTSTORAGE_KEY`, `NEXT_PUBLIC_RPC_URL`
- [ ] Rate-limit handling em todas as APIs externas
- [ ] Tema cyber aplicado (ver design-tokens.md)