# Template: AI Chat UI (Streaming + Tool Calls + Markdown)

Use quando o projeto envolve conversar com LLMs/IAs em interface (chatbot, assistente, copilot).

## Stack
- Next.js 15 (App Router) OU Electron + React
- Tailwind + shadcn/ui
- `react-markdown` + `remark-gfm` + `rehype-highlight` para renderizar markdown
- `shiki` ou `prismjs` para syntax highlighting
- SSE (EventSource) ou fetch stream para tokens progressivos
- Zustand para estado de mensagens/streaming

## Estrutura de dados
```ts
type ChatMessage = {
  id: string
  role: "user" | "assistant" | "system"
  content: string              // texto final ou em streaming
  toolCalls?: ToolCall[]
  timestamp: number
  isStreaming?: boolean
}
type ToolCall = {
  id: string
  name: string
  args: Record<string, unknown>
  result?: string
  status: "pending" | "running" | "done" | "error"
}
```

## SSE consumer (padrao)
```ts
async function sendMessage(text: string) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  })
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buf = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split("\n\n")
    buf = lines.pop() || ""
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const evt = JSON.parse(line.slice(6))
        handleEvent(evt)   // text_chunk | tool_start | tool_done | done | error
      }
    }
  }
}
```

## Message bubble (padrao visual)
```tsx
function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user"
  return (
    <div className={cn("flex gap-3 p-4", isUser && "flex-row-reverse")}>
      <Avatar />
      <div className={cn(
        "max-w-[75%] rounded-2xl px-4 py-2",
        isUser
          ? "bg-cyber-cyan/10 border border-cyber-cyan/30"
          : "bg-white/[0.02] border border-white/5"
      )}>
        {msg.toolCalls?.map(t => <ToolCallCard key={t.id} tool={t} />)}
        <Markdown content={msg.content} />
        {msg.isStreaming && <BlinkingCursor />}
      </div>
    </div>
  )
}
```

## Tool call visualization (collapsible)
```tsx
<div className="border border-cyber-purple/20 rounded-lg p-3 my-2 bg-cyber-purple/5">
  <div className="flex items-center gap-2 text-xs">
    <Wrench className="w-3 h-3" />
    <span className="font-mono">{tool.name}</span>
    <StatusDot status={tool.status} />
  </div>
  <details className="mt-2">
    <summary className="text-xs text-cyber-muted cursor-pointer">args / result</summary>
    <pre className="mt-1 text-xs overflow-x-auto">{JSON.stringify(tool, null, 2)}</pre>
  </details>
</div>
```

## Code block renderer (com copy button)
```tsx
function CodeBlock({ children, className }: any) {
  const lang = className?.replace("language-", "")
  return (
    <div className="relative group my-3 rounded-lg overflow-hidden border border-white/5">
      <div className="flex items-center justify-between px-3 py-1.5 bg-white/[0.03] text-xs text-cyber-muted">
        <span>{lang || "code"}</span>
        <button onClick={() => navigator.clipboard.writeText(children)}>copy</button>
      </div>
      <pre className="p-3 overflow-x-auto text-sm"><code>{children}</code></pre>
    </div>
  )
}
```

## Input com autoresize + atalhos
- Shift+Enter -> nova linha
- Enter -> enviar
- Cmd/Ctrl+K -> nova conversa
- Cmd/Ctrl+L -> limpar
- Slash commands opcionais

## Regras de entrega
1. Streaming SEMPRE (nunca buffer completo antes de mostrar)
2. Scroll automatico ao fundo em nova msg, pausar se usuario scrollou manualmente
3. Markdown renderizado com code blocks destacados
4. Tool calls visiveis mas colapsaveis (nao poluir)
5. Empty state convidativo (sugestoes de primeira pergunta)
6. Stop button durante streaming
7. Historico persistido (localStorage ou backend)