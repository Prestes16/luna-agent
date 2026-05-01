# Template: BUILD_MOBILE — Apps Mobile Solana/Web3/DeFi

## Stack Principal (por caso de uso)

### Solana DeFi Mobile → Expo + React Native
```
expo create meu-app --template expo-template-blank-typescript
cd meu-app
npx expo install @solana/web3.js @solana-mobile/wallet-adapter-mobile \
  @solana-mobile/mobile-wallet-adapter-protocol \
  @solana-mobile/mobile-wallet-adapter-protocol-web3js \
  @tanstack/react-query zustand react-native-mmkv \
  expo-secure-store expo-clipboard @gorhom/bottom-sheet \
  react-native-reanimated react-native-gesture-handler
```

### Web App Mobile-First (PWA) → Next.js responsivo
```
npx create-next-app@latest meu-app --app --tailwind --typescript
cd meu-app
npx shadcn@latest init -d
npm install @solana/web3.js @solana/wallet-adapter-react \
  @solana/wallet-adapter-base framer-motion
```

### Cross-platform Desktop+Mobile → Tauri + React
```
npm create tauri-app@latest meu-app -- --template react-ts
```

---

## Integrações Solana Mobile obrigatórias

### Mobile Wallet Adapter (dApp → carteira nativa)
```typescript
import { transact } from '@solana-mobile/mobile-wallet-adapter-protocol-web3js'
import { PublicKey, Transaction } from '@solana/web3.js'

// Conectar carteira (Phantom, Solflare, etc.)
const authResult = await transact(async (wallet) => {
  const authorizationResult = await wallet.authorize({
    cluster: 'mainnet-beta',
    identity: {
      name: 'Nome do App',
      uri: 'https://meuapp.com',
      icon: '/icon.png',
    },
  })
  return authorizationResult
})
```

### Helius RPC (WebSocket para feeds ao vivo)
```typescript
const connection = new Connection(
  `https://mainnet.helius-rpc.com/?api-key=${HELIUS_API_KEY}`,
  { wsEndpoint: `wss://mainnet.helius-rpc.com/?api-key=${HELIUS_API_KEY}` }
)

// Subscribe a mudanças de conta (saldo, posição DeFi)
connection.onAccountChange(publicKey, (accountInfo) => {
  // atualiza UI em tempo real
})
```

### Jupiter Swap (DeFi agregador)
```typescript
const { data: quoteResponse } = await fetch(
  `https://quote-api.jup.ag/v6/quote?inputMint=${inputMint}&outputMint=${outputMint}&amount=${amount}&slippageBps=50`
).then(r => r.json())

const { swapTransaction } = await fetch('https://quote-api.jup.ag/v6/swap', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ quoteResponse, userPublicKey: wallet.publicKey.toString() }),
}).then(r => r.json())
```

### Raydium Liquidity Pools
```typescript
import { Raydium } from '@raydium-io/raydium-sdk-v2'

const raydium = await Raydium.load({
  connection,
  owner: wallet.publicKey,
  disableFeatureCheck: true,
})

const poolInfo = await raydium.liquidity.getPoolInfo({ poolId })
```

---

## Estrutura de projeto (React Native / Expo)

```
src/
├── app/                    # Expo Router (file-based navigation)
│   ├── (tabs)/
│   │   ├── index.tsx       # Dashboard / Portfolio
│   │   ├── swap.tsx        # Swap DeFi
│   │   ├── pools.tsx       # Liquidity / Staking
│   │   └── wallet.tsx      # Carteira / NFTs
│   ├── _layout.tsx
│   └── +not-found.tsx
├── components/
│   ├── ui/                 # Componentes base com tema cyber
│   ├── WalletConnect.tsx   # Botão de conexão da carteira
│   ├── TokenBalance.tsx    # Saldo com logos de token
│   ├── SwapCard.tsx        # Card de swap
│   └── TxHistory.tsx       # Histórico de transações
├── hooks/
│   ├── useSolana.ts        # Connection + publicKey
│   ├── useBalance.ts       # SOL + SPL token balances
│   ├── useJupiter.ts       # Quotes + swaps
│   └── useDefi.ts          # Posições em pools/farms
├── store/
│   └── appStore.ts         # Zustand: wallet, tokens, settings
├── services/
│   ├── helius.ts           # RPC + WebSocket + DAS API
│   ├── jupiter.ts          # Swap aggregator
│   ├── raydium.ts          # Pools / LP
│   └── prices.ts           # Preços (Birdeye / CoinGecko)
└── constants/
    ├── tokens.ts           # Mints de tokens conhecidos (SOL, USDC, USDT...)
    └── programs.ts         # Program IDs dos protocolos
```

---

## Tela inicial obrigatória (nunca Hello World)

```typescript
// app/(tabs)/index.tsx — Portfolio Dashboard
export default function PortfolioDashboard() {
  const { publicKey } = useSolana()
  const { balances, totalUSD } = useBalance(publicKey)

  return (
    <SafeAreaView style={styles.container}>
      {/* Header com endereço e avatar */}
      <WalletHeader publicKey={publicKey} />

      {/* Total em USD com variação 24h */}
      <PortfolioValue total={totalUSD} />

      {/* Lista de tokens com logos e preços */}
      <TokenList balances={balances} />

      {/* Ações rápidas: Enviar | Receber | Swap */}
      <QuickActions />
    </SafeAreaView>
  )
}
```

---

## Tema visual mobile (tokens cyber adaptados para mobile)

```typescript
export const COLORS = {
  bg:       '#080b14',
  surface:  '#0d1117',
  border:   'rgba(0,212,255,0.12)',
  cyan:     '#00d4ff',
  purple:   '#7c3aed',
  green:    '#10b981',
  amber:    '#f59e0b',
  red:      '#ef4444',
  text:     '#e2e8f0',
  muted:    '#64748b',
}

// Fontes mono para valores financeiros (tabular-nums)
const styles = StyleSheet.create({
  value: { fontFamily: 'JetBrains Mono', fontVariant: ['tabular-nums'] },
  // ... resto dos estilos
})
```

---

## Checklist de entrega mobile

- [ ] Wallet connect funcionando (Phantom/Solflare via Mobile Wallet Adapter)
- [ ] Saldo SOL + principais SPL tokens exibidos
- [ ] Pelo menos 1 feature DeFi integrada (swap, pool, ou staking)
- [ ] Feed ao vivo via WebSocket Helius (não polling)
- [ ] Tratamento de erro para transação rejeitada / sem saldo
- [ ] Loading states em todas as operações on-chain
- [ ] Tema cyber aplicado (cores, fontes mono para valores)
- [ ] `npx expo start` sem erros antes de entregar
- [ ] Testado em iOS Simulator + Android Emulator (ou Expo Go)

---

## Anti-padrões mobile Solana

- ❌ Polling a cada N segundos — usar WebSocket Helius
- ❌ Guardar private key no app — usar Mobile Wallet Adapter
- ❌ Transação sem confirmação de assinatura do usuário
- ❌ Não tratar `WalletNotConnectedError`
- ❌ Aritmetica com floats em valores de token — usar BN ou lamports inteiros
- ❌ Hardcode de RPC público (rate limit agressivo) — usar Helius
- ❌ Sem slippage tolerance no swap — mínimo 0.5%
