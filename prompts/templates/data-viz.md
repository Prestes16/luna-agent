# Template: Data Visualization

Use para dashboards, graficos, analytics.

## Stack
- recharts para graficos padrao (responsivo, bom default)
- tremor para dashboards rapidos com cards de metrica
- react-grid-layout se precisar draggable/resizable
- date-fns para manipulacao de datas

## Setup
```bash
npm i recharts date-fns
# OU tremor (inclui recharts internamente)
npm i @tremor/react
```

## Padroes
- Sempre mostrar loading skeleton antes dos dados
- Tooltip customizado alinhado ao tema cyber
- Cores dos graficos da paleta: cyan, purple, green, orange
- Eixos com labels claros e unidades (%, MB, USD)
- Legenda movel para mobile (abaixo do grafico)
- Dados vazios: estado explicito "Sem dados ainda" + CTA

## Grafico exemplo
```tsx
<ResponsiveContainer width="100%" height={300}>
  <AreaChart data={data}>
    <defs>
      <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
        <stop offset="5%" stopColor="#00d4ff" stopOpacity={0.4}/>
        <stop offset="95%" stopColor="#00d4ff" stopOpacity={0}/>
      </linearGradient>
    </defs>
    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,212,255,0.1)"/>
    <XAxis dataKey="date" stroke="#8b949e"/>
    <YAxis stroke="#8b949e"/>
    <Tooltip contentStyle={{background:"#0a0f1e",border:"1px solid rgba(0,212,255,0.3)"}}/>
    <Area type="monotone" dataKey="value" stroke="#00d4ff" fill="url(#g1)"/>
  </AreaChart>
</ResponsiveContainer>
```