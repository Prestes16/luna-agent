# Template: Web3 UI/UX Patterns — PC + Mobile

Biblioteca de componentes e padroes UI/UX especificos para dApps Solana, launchpads, carteiras e DeFi. **Complemento obrigatorio** a `ui-components.md` (PC) e `solana-mobile-defi.md` (mobile).

Leia ANTES de construir qualquer UI de trade/launchpad/portfolio. Todos os componentes aqui ja vem com tema cyber aplicado.

---

## Stack de referencia

**PC (Next.js + shadcn):**
```bash
npm i framer-motion lightweight-charts lucide-react sonner \
  @radix-ui/react-dialog @radix-ui/react-tooltip \
  tailwind-merge clsx numeral
```

**Mobile (Expo):**
```bash
npx expo install @gorhom/bottom-sheet @shopify/flash-list \
  react-native-reanimated react-native-gesture-handler \
  react-native-svg expo-haptics
npm i react-native-wagmi-charts numeral
```

---

## Tokens visuais compartilhados

```typescript
// tokens.ts — usar em PC (Tailwind config) e Mobile (StyleSheet)
export const CYBER = {
  bg:        '#080b14',
  surface:   '#0d1117',
  surface2:  '#121826',
  border:    'rgba(0,212,255,0.12)',
  borderHi:  'rgba(0,212,255,0.3)',
  cyan:      '#00d4ff',
  purple:    '#7c3aed',
  green:     '#10b981',
  red:       '#ef4444',
  amber:     '#f59e0b',
  text:      '#e2e8f0',
  muted:     '#64748b',
  dim:       '#475569',
}

export const MONO = 'JetBrains Mono, ui-monospace, monospace'
```

---

## Componente 1 — ValueText (valores financeiros)

Regra de ouro: TODO numero financeiro usa fonte mono + tabular-nums + cor por sinal.

### PC (React)
```tsx
// components/ValueText.tsx
import numeral from 'numeral'

export function ValueText({
  value, prefix = '', suffix = '',
  variant = 'neutral', format = '0,0.00',
  size = 'md',
}: {
  value: number; prefix?: string; suffix?: string
  variant?: 'neutral' | 'up' | 'down' | 'auto'
  format?: string; size?: 'sm' | 'md' | 'lg' | 'xl'
}) {
  const v = variant === 'auto' ? (value > 0 ? 'up' : value < 0 ? 'down' : 'neutral') : variant
  const color = v === 'up' ? 'text-emerald-400'
              : v === 'down' ? 'text-red-400'
              : 'text-cyan-300'
  const sz = { sm: 'text-xs', md: 'text-sm', lg: 'text-base', xl: 'text-2xl' }[size]
  return (
    <span className={`font-mono tabular-nums ${color} ${sz}`}>
      {v === 'up' ? '+' : ''}{prefix}{numeral(value).format(format)}{suffix}
    </span>
  )
}
```

### Mobile (React Native)
```tsx
import { Text, StyleSheet } from 'react-native'
import numeral from 'numeral'

export function ValueText({ value, variant='neutral', prefix='', suffix='', format='0,0.00' }) {
  const color = variant === 'up' ? '#10b981'
              : variant === 'down' ? '#ef4444'
              : '#67e8f9'
  return (
    <Text style={[styles.value, { color }]}>
      {variant === 'up' ? '+' : ''}{prefix}{numeral(value).format(format)}{suffix}
    </Text>
  )
}
const styles = StyleSheet.create({
  value: { fontFamily: 'JetBrainsMono-Regular', fontVariant: ['tabular-nums'] },
})
```

---

## Componente 2 — TokenRow (lista de tokens)

Layout: avatar 32px | nome+symbol | saldo+USD | Δ24h

### PC
```tsx
export function TokenRow({ token }: { token: TokenData }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-cyan-500/10
      hover:border-cyan-500/30 hover:bg-cyan-500/5 transition-all cursor-pointer">
      <img src={token.image} alt="" className="w-8 h-8 rounded-full bg-slate-800" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium truncate">{token.name}</span>
          <span className="text-[10px] text-slate-500 uppercase">{token.symbol}</span>
        </div>
        <ValueText value={token.balance} suffix={` ${token.symbol}`} size="sm" variant="neutral" />
      </div>
      <div className="text-right">
        <ValueText value={token.usdValue} prefix="$" size="md" variant="neutral" />
        <ValueText value={token.change24h} suffix="%" size="sm" variant="auto" format="0,0.00" />
      </div>
    </div>
  )
}
```

### Mobile (com FlashList)
```tsx
import { FlashList } from '@shopify/flash-list'
import { Pressable, View, Image, Text } from 'react-native'
import * as Haptics from 'expo-haptics'

function TokenRowRN({ token, onPress }) {
  return (
    <Pressable
      onPress={() => { Haptics.selectionAsync(); onPress(token) }}
      style={({ pressed }) => [styles.row, pressed && { opacity: 0.7 }]}
    >
      <Image source={{ uri: token.image }} style={styles.avatar} />
      <View style={{ flex: 1 }}>
        <Text style={styles.name}>{token.name}</Text>
        <ValueText value={token.balance} suffix={` ${token.symbol}`} />
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        <ValueText value={token.usdValue} prefix="$" />
        <ValueText value={token.change24h} suffix="%" variant={token.change24h >= 0 ? 'up' : 'down'} />
      </View>
    </Pressable>
  )
}

// Uso: <FlashList data={tokens} estimatedItemSize={60} renderItem={({item}) => <TokenRowRN token={item} />} />
```

---

## Componente 3 — Trade Panel (launchpad/swap)

### PC — sidebar direita fixa
```tsx
export function TradePanel({ mint }: { mint: string }) {
  const [mode, setMode] = useState<'buy'|'sell'>('buy')
  const [amount, setAmount] = useState('')
  const [slippage, setSlippage] = useState(1)
  const [priorityFee, setPriorityFee] = useState<'slow'|'fast'|'turbo'>('fast')
  const { quote, isLoading } = useQuote(mint, mode, amount, slippage)

  return (
    <div className="p-4 rounded-xl border border-cyan-500/15 bg-slate-900/60 backdrop-blur
      space-y-3 sticky top-20">
      {/* Buy/Sell toggle */}
      <div className="grid grid-cols-2 gap-1 p-1 rounded-lg bg-slate-800/60">
        {(['buy','sell'] as const).map(m => (
          <button key={m} onClick={() => setMode(m)}
            className={`py-2 rounded-md text-sm font-medium transition-all ${
              mode === m
                ? (m === 'buy' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300')
                : 'text-slate-400 hover:text-slate-200'
            }`}>{m === 'buy' ? 'Comprar' : 'Vender'}</button>
        ))}
      </div>

      {/* Input */}
      <AmountInput value={amount} onChange={setAmount} unit={mode === 'buy' ? 'SOL' : 'TOKEN'} />

      {/* Slippage + priority */}
      <SlippageControl value={slippage} onChange={setSlippage} max={50} />
      <PriorityFeeSelect value={priorityFee} onChange={setPriorityFee} />

      {/* Preview */}
      {quote && (
        <div className="space-y-1.5 p-3 rounded-lg bg-slate-800/40 text-xs">
          <Row label="Min recebido" value={<ValueText value={quote.minOut} suffix=" tokens" />} />
          <Row label="Price impact" value={<ValueText value={quote.impact} suffix="%" variant={quote.impact > 3 ? 'down' : 'neutral'} />} />
          <Row label="Taxa rede" value={<ValueText value={quote.networkFee} prefix="~" suffix=" SOL" format="0,0.0000" />} />
          <Row label="Taxa plataforma" value={<ValueText value={quote.platformFee} suffix=" SOL" />} />
        </div>
      )}

      {/* CTA */}
      <button disabled={!quote || isLoading}
        className={`w-full py-3 rounded-lg font-semibold transition-all ${
          mode === 'buy'
            ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 hover:shadow-[0_0_24px_rgba(16,185,129,0.35)]'
            : 'bg-red-500 hover:bg-red-400 text-slate-950 hover:shadow-[0_0_24px_rgba(239,68,68,0.35)]'
        } disabled:opacity-40 disabled:cursor-not-allowed`}>
        {isLoading ? 'Carregando...' : mode === 'buy' ? `Comprar ${amount} SOL` : `Vender ${amount}`}
      </button>
    </div>
  )
}
```

### Mobile — bottom sheet 3 snap points
```tsx
import BottomSheet, { BottomSheetView } from '@gorhom/bottom-sheet'

export function TradeBottomSheet({ mint, onClose }: { mint: string; onClose: () => void }) {
  const snapPoints = useMemo(() => ['25%', '60%', '95%'], [])
  return (
    <BottomSheet
      snapPoints={snapPoints}
      backgroundStyle={{ backgroundColor: '#0d1117' }}
      handleIndicatorStyle={{ backgroundColor: '#00d4ff', width: 40 }}
      onClose={onClose}
    >
      <BottomSheetView style={{ padding: 16 }}>
        {/* Snap 25%: header + quick buy/sell buttons */}
        {/* Snap 60%: amount input + slippage slider + preview */}
        {/* Snap 95%: full confirmation + biometric button */}
        <TradeContent mint={mint} />
      </BottomSheetView>
    </BottomSheet>
  )
}
```

Regra mobile: botao de confirmar assinatura SEMPRE dispara `LocalAuthentication.authenticateAsync()` antes de chamar `signAndSend`.

---

## Componente 4 — Bonding Curve Progress

Mostra quanto falta para graduar em AMM.

```tsx
export function BondingProgress({ current, target = 85 }: { current: number; target?: number }) {
  const pct = Math.min(100, (current / target) * 100)
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">Bonding curve</span>
        <span className="font-mono tabular-nums text-cyan-300">
          {current.toFixed(2)} / {target} SOL ({pct.toFixed(1)}%)
        </span>
      </div>
      <div className="h-2 rounded-full bg-slate-800/60 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-purple-500
            transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      {pct >= 100 && (
        <div className="text-xs text-emerald-400 font-medium">
          🎓 Graduado! Token agora disponivel no AMM.
        </div>
      )}
    </div>
  )
}
```

Mobile: mesma logica com `View` + `Animated.View` para barra + `react-native-reanimated` para suavizar.

---

## Componente 5 — Safety Badges

Mostra status de seguranca de um token.

```tsx
export function SafetyBadges({ token }: { token: TokenDetail }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge
        label="Mint revoked"
        ok={token.mintAuthority === null}
        tooltip="Autoridade de mint revogada — supply fixo"
      />
      <Badge
        label="Freeze revoked"
        ok={token.freezeAuthority === null}
        tooltip="Autoridade de freeze revogada — ninguem pode congelar sua carteira"
      />
      <Badge
        label="LP locked"
        ok={token.lpLocked}
        tooltip="Liquidez travada — anti-rug"
      />
      <Badge
        label={`Top 10: ${token.top10Pct.toFixed(1)}%`}
        ok={token.top10Pct < 30}
        warn={token.top10Pct >= 30 && token.top10Pct < 50}
        tooltip="Concentracao nos top 10 holders"
      />
      {token.honeypot && (
        <Badge label="HONEYPOT" danger tooltip="Simulacao de venda falhou — nao compre" />
      )}
    </div>
  )
}

function Badge({ label, ok, warn, danger, tooltip }: any) {
  const cls = danger
    ? 'bg-red-500/20 text-red-300 border-red-500/40'
    : warn
    ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
    : ok
    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
    : 'bg-slate-700/30 text-slate-400 border-slate-600/30'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-mono ${cls}`}
      title={tooltip}>
      {ok && !danger && <CheckCircle2 size={10} />}
      {(!ok || danger) && <AlertTriangle size={10} />}
      {label}
    </span>
  )
}
```

---

## Componente 6 — Wizard multi-step (criacao de token)

Barra de progresso + etapas navegaveis.

```tsx
const STEPS = ['metadata','economia','curva','preview','deploy'] as const

export function LaunchWizard() {
  const [step, setStep] = useState(0)
  const [data, setData] = useState<LaunchData>(initialLaunchData)

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <StepIndicator current={step} total={STEPS.length} labels={STEPS} />
      <AnimatePresence mode="wait">
        <motion.div key={step}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.2 }}>
          {step === 0 && <StepMetadata data={data} onChange={setData} />}
          {step === 1 && <StepEconomy data={data} onChange={setData} />}
          {step === 2 && <StepCurve data={data} onChange={setData} />}
          {step === 3 && <StepPreview data={data} />}
          {step === 4 && <StepDeploy data={data} />}
        </motion.div>
      </AnimatePresence>
      <NavButtons step={step} setStep={setStep} total={STEPS.length} canAdvance={isValid(step, data)} />
    </div>
  )
}
```

Mobile: mesmo fluxo mas cada step e um bottom sheet cheio (`snapPoints: ['95%']`) com `KeyboardAvoidingView`.

---

## Componente 7 — Chart ao vivo

### PC (lightweight-charts)
```tsx
import { createChart, ColorType } from 'lightweight-charts'

useEffect(() => {
  const chart = createChart(ref.current!, {
    layout: { background: { type: ColorType.Solid, color: '#080b14' }, textColor: '#e2e8f0' },
    grid: { vertLines: { color: 'rgba(0,212,255,0.05)' }, horzLines: { color: 'rgba(0,212,255,0.05)' } },
    width: ref.current!.clientWidth, height: 360,
  })
  const series = chart.addCandlestickSeries({
    upColor: '#10b981', downColor: '#ef4444',
    borderVisible: false, wickUpColor: '#10b981', wickDownColor: '#ef4444',
  })
  series.setData(candles)
  const unsub = subscribeTrades(mint, (trade) => {
    const last = series.data()[series.data().length - 1] as any
    series.update({ ...last, close: trade.price, high: Math.max(last.high, trade.price), low: Math.min(last.low, trade.price) })
  })
  return () => { unsub(); chart.remove() }
}, [mint])
```

### Mobile (react-native-wagmi-charts)
```tsx
import { LineChart } from 'react-native-wagmi-charts'
<LineChart.Provider data={points}>
  <LineChart height={240}>
    <LineChart.Path color="#00d4ff" width={2}>
      <LineChart.Gradient color="#00d4ff" />
    </LineChart.Path>
    <LineChart.CursorCrosshair color="#00d4ff" />
  </LineChart>
  <LineChart.PriceText format={({ value }) => `$${value.toFixed(6)}`} />
</LineChart.Provider>
```

---

## Componente 8 — Estados (loading / empty / error)

Proibido spinner generico. Sempre contexto + acao.

### Skeleton (PC + Mobile)
```tsx
export function TokenRowSkeleton() {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 animate-pulse">
      <div className="w-8 h-8 rounded-full bg-slate-800/60" />
      <div className="flex-1 space-y-1.5">
        <div className="h-3 w-24 rounded bg-slate-800/60" />
        <div className="h-2 w-16 rounded bg-slate-800/40" />
      </div>
      <div className="h-3 w-16 rounded bg-slate-800/60" />
    </div>
  )
}
```

### Empty state
```tsx
<div className="flex flex-col items-center justify-center py-16 text-center">
  <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/20
    flex items-center justify-center mb-4">
    <Inbox size={28} className="text-cyan-400" />
  </div>
  <h3 className="text-sm font-semibold text-slate-200">Nenhum token ainda</h3>
  <p className="text-xs text-slate-500 mt-1 max-w-sm">
    Conecte sua carteira ou crie seu primeiro token usando o wizard.
  </p>
  <button className="mt-4 px-4 py-2 rounded-lg bg-cyan-500 text-slate-950 text-sm font-medium">
    Criar token
  </button>
</div>
```

### Error state com retry
```tsx
<div className="flex items-start gap-3 p-4 rounded-lg bg-red-500/10 border border-red-500/30">
  <AlertCircle size={18} className="text-red-400 flex-shrink-0 mt-0.5" />
  <div className="flex-1">
    <p className="text-sm text-red-300 font-medium">Falha ao carregar preco</p>
    <p className="text-xs text-red-400/80 mt-1">{error.message}</p>
    <button onClick={retry} className="mt-2 text-xs text-cyan-400 hover:text-cyan-300 underline">
      Tentar novamente
    </button>
  </div>
</div>
```

---

## Componente 9 — Confirmacao de transacao

### PC (shadcn Dialog)
```tsx
<Dialog open={confirming} onOpenChange={setConfirming}>
  <DialogContent className="bg-slate-900 border-cyan-500/20">
    <DialogHeader>
      <DialogTitle>Confirmar transacao</DialogTitle>
    </DialogHeader>
    <div className="space-y-3">
      <AddressRow label="Para" address={to} />  {/* mostra 4+4 chars + copy */}
      <Row label="Valor" value={<ValueText value={amount} suffix=" SOL" size="lg" />} />
      <Row label="Rede" value="Mainnet Beta" />
      <Row label="Taxa estimada" value={<ValueText value={fee} suffix=" SOL" format="0,0.0000" />} />
      <div className="p-2 rounded bg-amber-500/10 border border-amber-500/30 text-[11px] text-amber-300">
        Revise os detalhes. Transacoes Solana sao irreversiveis.
      </div>
    </div>
    <DialogFooter>
      <button onClick={() => setConfirming(false)}>Cancelar</button>
      <button onClick={handleSign} className="bg-cyan-500 text-slate-950 font-medium">Assinar</button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

### Mobile (bottom sheet + biometria)
```tsx
async function handleConfirm() {
  const bio = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Confirme com biometria para assinar',
    cancelLabel: 'Cancelar',
  })
  if (!bio.success) { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error); return }
  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
  const sig = await signAndSend(tx, authToken)
  Toast.show({ text1: 'Transacao enviada', text2: sig.slice(0,12)+'...' })
}
```

---

## Componente 10 — AddressRow (checksum visual)

```tsx
export function AddressRow({ label, address }: { label?: string; address: string }) {
  const short = `${address.slice(0,4)}...${address.slice(-4)}`
  return (
    <div className="flex items-center justify-between text-xs">
      {label && <span className="text-slate-400">{label}</span>}
      <button onClick={() => { navigator.clipboard.writeText(address); toast('Copiado') }}
        className="flex items-center gap-1.5 font-mono text-cyan-300 hover:text-cyan-200">
        <span>{short}</span>
        <Copy size={10} />
      </button>
    </div>
  )
}
```

Valido em PC e Mobile (mobile usa `expo-clipboard`).

---

## Regras UX nao-negociaveis (PC + Mobile)

1. **Valores financeiros** — sempre fonte mono + `tabular-nums` + cor por sinal
2. **Confirmacao de tx** — PC: modal com todos os numeros. Mobile: bottom sheet + biometria obrigatoria
3. **Loading** — skeleton especifico, nunca spinner centralizado
4. **Empty state** — icone + mensagem humana + CTA
5. **Error state** — icone vermelho + mensagem + botao retry
6. **Toasts** — usar sonner (PC) ou react-native-toast-message (mobile). Sucesso: link Solscan. Erro: causa + retry
7. **Enderecos** — sempre mostrar 4+4 chars com copy button, nunca endereco inteiro
8. **Preco impact > 3%** — alerta amber. > 10% — bloquear com confirmacao dupla
9. **Slippage** — input ajustavel, cap em 50%. Mostrar aviso acima de 5%
10. **Mobile touch targets** — minimo 48×48 dp sempre
11. **SafeArea** — toda tela mobile
12. **Haptics** — `selectionAsync` em toque, `success`/`error` em resultado de tx
13. **Animacoes** — 200ms max em hover, 300ms em transicoes de tela. Nunca bounce em dApp serio

---

## Layout base (ambas plataformas)

### PC — grid de 3 colunas para detalhe de token
```
┌──────────────────────────────────────────────────────────┐
│  [Header: logo + wallet button + network indicator]      │
├─────────┬─────────────────────────────────┬──────────────┤
│ Sidebar │    Chart + trades + holders     │ Trade panel  │
│ nav     │                                 │ (sticky top) │
└─────────┴─────────────────────────────────┴──────────────┘
```

### Mobile — tab bar + bottom sheet trade
```
┌─────────────────────┐
│ Header (safe top)   │
├─────────────────────┤
│                     │
│  Token detail page  │
│  (scroll)           │
│                     │
├─────────────────────┤
│ [Buy]    [Sell]     │  <- fixed bottom bar
└─────────────────────┘
     ↑ tap abre BottomSheet 3-snap
```

---

## Checklist UI/UX launchpad + DeFi

- [ ] `ValueText` aplicado em TODO numero financeiro
- [ ] `TokenRow` em toda lista de token
- [ ] `TradePanel` (PC) ou `TradeBottomSheet` (mobile) funcional com preview antes de assinar
- [ ] `BondingProgress` em paginas de tokens em curva
- [ ] `SafetyBadges` no detalhe de cada token
- [ ] `LaunchWizard` multi-step para criacao
- [ ] Chart ao vivo com stream de trades
- [ ] Skeleton em loading, empty state com CTA, error com retry
- [ ] `AddressRow` com checksum visual 4+4
- [ ] Biometria antes de assinar no mobile
- [ ] Toast com link Solscan apos sucesso
- [ ] Haptics em toques e confirmacoes (mobile)
- [ ] Tema cyber consistente (design-tokens.md aplicado)
- [ ] Responsive em PC (<1200px colapsa sidebar)
- [ ] SafeArea + tabular-nums + 48dp touch targets (mobile)