# Template: SOLANA_MOBILE_DEFI — apps mobile-first Solana/Web3/DeFi

Upgrade de `mobile-app.md` para apps com foco principal em DeFi/Web3 na rede Solana.
Leia AMBOS antes de construir: primeiro `mobile-app.md` (stack base), depois este (padrões avançados).

---

## Quando usar este template

Sinais na mensagem do usuário:
- "app mobile solana", "dapp mobile", "defi mobile", "wallet mobile"
- "swap mobile", "portfolio crypto mobile", "staking mobile", "NFT mobile"
- "bounty tracker mobile", "tracker defi mobile", "sign in with solana"

Se for apenas site mobile-first (PWA sem carteira nativa) → use `nextjs-app.md`.
Se for app mobile sem Solana → use `mobile-app.md` sozinho.

---

## Stack de referência (production-grade)

```bash
# 1. Scaffold Expo TS estrito
npx create-expo-app@latest meu-dapp -t
cd meu-dapp

# 2. Core Solana + Mobile Wallet Adapter
npx expo install @solana/web3.js \
  @solana-mobile/mobile-wallet-adapter-protocol \
  @solana-mobile/mobile-wallet-adapter-protocol-web3js \
  @solana-mobile/wallet-adapter-mobile \
  @solana/spl-token \
  buffer react-native-get-random-values

# 3. DeFi + dados ao vivo
npm install @jup-ag/api @pythnetwork/price-service-client \
  bn.js bs58 borsh

# 4. Estado + cache + storage seguro
npx expo install @tanstack/react-query zustand \
  react-native-mmkv expo-secure-store expo-crypto expo-clipboard

# 5. UI mobile-first
npx expo install @gorhom/bottom-sheet react-native-reanimated \
  react-native-gesture-handler react-native-svg \
  expo-haptics expo-local-authentication @shopify/flash-list
```

---

## Arquitetura recomendada

```
app/
  (tabs)/
    index.tsx          # Portfolio (home)
    swap.tsx           # Jupiter swap
    stake.tsx          # Staking/Yield
    activity.tsx       # Histórico
  _layout.tsx          # TabBar + SafeArea + Toaster
src/
  solana/
    connection.ts      # Helius RPC com WebSocket
    mwa.ts             # Mobile Wallet Adapter helpers
    jupiter.ts         # Swap via @jup-ag/api
    prices.ts          # Pyth / Jupiter price feeds
    das.ts             # Helius DAS API (NFTs, tokens enriquecidos)
  hooks/
    useWallet.ts
    useBalance.ts
    usePortfolio.ts
    useSwapQuote.ts
  stores/
    walletStore.ts     # Zustand + MMKV (não-sensível) / SecureStore (sensível)
  ui/
    TokenRow.tsx
    ValueText.tsx      # tabular-nums + cor por sinal
    BottomSheetSwap.tsx
    QRReceive.tsx
```

---

## Padrão 1 — Conexão de carteira (MWA)

```typescript
// src/solana/mwa.ts
import "react-native-get-random-values"
import { Buffer } from "buffer"
global.Buffer = Buffer
import { transact } from "@solana-mobile/mobile-wallet-adapter-protocol-web3js"
import { PublicKey, Transaction, VersionedTransaction } from "@solana/web3.js"

const APP_IDENTITY = {
  name: "Nome do dApp",
  uri: "https://meuapp.com",
  icon: "favicon.ico",
}

export async function connectWallet(cluster: "mainnet-beta" | "devnet" = "mainnet-beta") {
  return transact(async (wallet) => {
    const auth = await wallet.authorize({ cluster, identity: APP_IDENTITY })
    return {
      publicKey: new PublicKey(auth.accounts[0].address),
      authToken: auth.auth_token,
      label: auth.accounts[0].label ?? "Wallet",
    }
  })
}

export async function signAndSend(tx: Transaction | VersionedTransaction, authToken: string) {
  return transact(async (wallet) => {
    await wallet.reauthorize({ auth_token: authToken, identity: APP_IDENTITY })
    const sigs = await wallet.signAndSendTransactions({ transactions: [tx] })
    return sigs[0]
  })
}
```

`authToken` → `expo-secure-store` (Keychain/Keystore). **Nunca** AsyncStorage ou MMKV puro.

---

## Padrão 2 — Helius RPC com WebSocket (substitui polling)

```typescript
// src/solana/connection.ts
import { Connection, PublicKey } from "@solana/web3.js"

const API_KEY = process.env.EXPO_PUBLIC_HELIUS_KEY!
export const connection = new Connection(
  `https://mainnet.helius-rpc.com/?api-key=${API_KEY}`,
  {
    commitment: "confirmed",
    wsEndpoint: `wss://mainnet.helius-rpc.com/?api-key=${API_KEY}`,
  }
)

export function subscribeBalance(pubkey: PublicKey, cb: (lamports: number) => void) {
  const id = connection.onAccountChange(pubkey, (info) => cb(info.lamports), "confirmed")
  return () => connection.removeAccountChangeListener(id)
}
```

---

## Padrão 3 — Swap Jupiter v6

```typescript
// src/solana/jupiter.ts
import { createJupiterApiClient } from "@jup-ag/api"
import { VersionedTransaction } from "@solana/web3.js"
import { Buffer } from "buffer"

const jup = createJupiterApiClient()

export async function getQuote(input: string, output: string, amount: bigint, slippageBps = 50) {
  return jup.quoteGet({
    inputMint: input, outputMint: output,
    amount: Number(amount), slippageBps,
    onlyDirectRoutes: false,
  })
}

export async function buildSwapTx(quote: any, userPubkey: string) {
  const { swapTransaction } = await jup.swapPost({
    swapRequest: {
      quoteResponse: quote,
      userPublicKey: userPubkey,
      wrapAndUnwrapSol: true,
      dynamicComputeUnitLimit: true,
      prioritizationFeeLamports: "auto",
    },
  })
  return VersionedTransaction.deserialize(Buffer.from(swapTransaction, "base64"))
}
```

Regras no swap:
- `slippageBps` mínimo 50 (0.5%), ajustável até 300 (3%)
- `prioritizationFeeLamports: "auto"`
- Mostrar: rota, price impact, min received, taxa de rede
- Biometria (`expo-local-authentication`) antes de assinar

---

## Padrão 4 — Helius DAS (portfolio enriquecido)

```typescript
// src/solana/das.ts
export async function getAssetsByOwner(owner: string, page = 1) {
  const r = await fetch(`https://mainnet.helius-rpc.com/?api-key=${process.env.EXPO_PUBLIC_HELIUS_KEY}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0", id: "portfolio", method: "getAssetsByOwner",
      params: { ownerAddress: owner, page, limit: 100, displayOptions: { showFungible: true } },
    }),
  })
  const { result } = await r.json()
  return result
}
```

---

## Padrão 5 — Preços ao vivo via Pyth (Hermes)

```typescript
import { PriceServiceConnection } from "@pythnetwork/price-service-client"
const pyth = new PriceServiceConnection("https://hermes.pyth.network")

export function subscribePrices(ids: string[], cb: (id: string, price: number) => void) {
  pyth.subscribePriceFeedUpdates(ids, (f) => {
    const p = f.getPriceUnchecked()
    cb(f.id, Number(p.price) * 10 ** p.expo)
  })
  return () => pyth.unsubscribePriceFeedUpdates(ids)
}
```

---

## Padrão 6 — Sign In With Solana

```typescript
export async function signInWithSolana(publicKey: PublicKey, authToken: string) {
  const nonce = await fetch("/api/auth/nonce").then(r => r.json())
  const message = `${APP_IDENTITY.name} quer verificar: ${publicKey.toBase58()}\nnonce: ${nonce}`
  return transact(async (wallet) => {
    await wallet.reauthorize({ auth_token: authToken, identity: APP_IDENTITY })
    const signed = await wallet.signMessages({
      addresses: [publicKey.toBase58()],
      payloads: [Buffer.from(message).toString("base64")],
    })
    return fetch("/api/auth/verify", {
      method: "POST",
      body: JSON.stringify({ signature: signed.signed_payloads[0], message, publicKey: publicKey.toBase58() }),
    })
  })
}
```

---

## UX mobile-first (obrigatório)

- Touch targets 48×48 dp mínimos
- `SafeAreaView` sempre — notch e status bar
- Bottom sheets (`@gorhom/bottom-sheet`) para confirmações, nunca modais centralizados
- Haptics (`expo-haptics`) em confirmações e erros
- Biometria antes de qualquer assinatura
- Skeleton screens, nunca spinners centralizados
- Pull-to-refresh em listas
- Offline banner via `@react-native-community/netinfo`
- Fonte mono tabular em TODOS os valores financeiros
- Verde `#10b981` ganho, vermelho `#ef4444` perda, cyan `#00d4ff` neutro
- `FlashList` para listas com 50+ itens

---

## Segurança Solana mobile — não-negociável

- Nunca armazenar private key — MWA delega à carteira
- `authToken` apenas em `expo-secure-store`
- Validar `lastValidBlockHeight` antes de reenviar tx
- Usar `VersionedTransaction` (v0)
- Mostrar hash + link Solscan após sucesso
- Refetch saldo antes de swap — nunca confiar em cache
- Validar destinatário com `PublicKey.isOnCurve()` + checksum visual (4+4 chars)
- `simulateTransaction` antes de assinar em valores altos
- Nunca hardcodar mint addresses — usar Jupiter strict list

---

## Checklist de entrega

- [ ] MWA: connect + reauthorize + signAndSend + signMessage
- [ ] Helius RPC com WebSocket (API key em `.env`)
- [ ] DAS retornando portfolio com logos e preços
- [ ] Pyth subscrito para tokens principais
- [ ] Jupiter swap com rota visível + slippage ajustável
- [ ] Biometria antes de assinar
- [ ] Bottom sheet para detalhes de tx
- [ ] Haptic feedback em confirmações/erros
- [ ] Telas: Portfolio, Swap, Stake/Activity, Settings
- [ ] SafeArea + tabular-nums + tema cyber
- [ ] `npx expo start` limpo
- [ ] Testado em device físico (iOS + Android)
- [ ] `.env.example` com `EXPO_PUBLIC_HELIUS_KEY`

---

## Anti-padrões DeFi mobile

- ❌ Swap sem rota ou price impact visível
- ❌ Slippage fixo sem ajuste do usuário
- ❌ Reutilizar blockhash em retry
- ❌ Mostrar lamports em vez de SOL
- ❌ Swap/transfer > $100 sem simulação prévia
- ❌ Seed phrase na RAM mesmo "temporariamente"
- ❌ Animações pesadas em listas 100+ — use FlashList
- ❌ Requests sequenciais de preço token por token — use batch