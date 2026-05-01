# Luna Agent — Smoke Checklist (E2E Manual)

> Execute após cada deploy ou alteração significativa.
> Marca ✅ quando passar, ❌ quando falhar (anota o erro).

---

## 0. Pré-requisitos

- [ ] VPS com Docker rodando (`docker ps` mostra `luna-agent`)
- [ ] Bridge local rodando (`python local_bridge.py` no PC local)
- [ ] Túnel SSH ativo (`ssh -L 8000:localhost:8000 <vps>`)
- [ ] UI acessível em `http://localhost:8000`

---

## 1. Backend API (automático)

```bash
python scripts/smoke_backend.py http://localhost:8000
```

- [ ] Todos os checks passam
- [ ] `target_root` não é `invalid_target_root`

---

## 2. Bridge Local (automático)

```bash
python scripts/smoke_bridge.py http://127.0.0.1:8765
```

- [ ] `/health` retorna `"bridge": "local"`
- [ ] `/screen/status` retorna `available: true`
- [ ] `/screen/capture` retorna `image_b64` com dados

---

## 3. UI — Chat

1. Abre `http://localhost:8000`
2. No painel Chat, digita: `"Olá Luna, está funcionando?"`
3. Pressiona Enter

- [ ] Mensagem aparece no histórico (bolha azul)
- [ ] Indicador "typing..." aparece e some
- [ ] Resposta da Luna aparece (bolha escura)
- [ ] Sem erros no console do browser (F12)

---

## 4. UI — Bridge Status

1. No painel Agente, localiza seção `// observação local`
2. O badge de status mostra "alvo: VPS" por padrão

- [ ] Badge mostra "alvo: VPS"
- [ ] Botão "Capturar tela" está **desabilitado**

3. Clica no botão **LOCAL** (target switch)

- [ ] Badge muda para "alvo: LOCAL"
- [ ] Status "bridge" muda para "bridge online" (verde) ou "bridge offline" (vermelho)
- [ ] Botão "Capturar tela" fica **habilitado**

---

## 5. UI — Captura de Tela (requer bridge online + target=LOCAL)

1. Com target=LOCAL e bridge online
2. Clica em "📷 Capturar tela"

- [ ] Botão mostra "⏳ Capturando..." durante operação
- [ ] Preview da captura aparece na UI
- [ ] Metadados aparecem: timestamp, resolução, tamanho
- [ ] Sem erros JS no console
- [ ] Botão "🔍 Analisar" aparece após captura

3. Clica em "🔍 Analisar"

- [ ] Área de análise aparece
- [ ] Texto de análise visual é retornado (pode demorar ~3s)

---

## 6. UI — Agent Plan (Planejar)

1. Abre o painel **Agente**
2. No campo objetivo, digita: `"Listar arquivos do workspace"`
3. Seleciona modo "Propose"
4. Clica em **⬡ Planejar**

- [ ] Toast aparece com mensagem (ex: "Plano gerado: 1 ação(ões)")
- [ ] Sem `ReferenceError: showToast` no console
- [ ] Seção "// aprovação pendente" ou "// execução automática" aparece com a ação
- [ ] Seção "// estado do sistema" atualiza com o objetivo e configuração

---

## 7. UI — Aprovação e Execução

1. Com um plano gerado (passo 6)
2. Na seção "// aprovação pendente", expande a ação (clica no header)
3. Clica em "✓ Aprovar"

- [ ] Toast "✓ Aprovada: act-xxxx" aparece
- [ ] Seção auditoria atualiza (mostra entrada "approved")
- [ ] Botão "▶ Executar agora" aparece

4. Clica em "▶ Executar agora"

- [ ] Toast "Ação executada!" ou mensagem de resultado aparece
- [ ] Seção "// último resultado" atualiza com resultado da execução
- [ ] Seção auditoria atualiza com nova entrada

---

## 8. UI — Auditoria Visível

1. Após aprovação/execução (passo 7)
2. Seção "// auditoria" no painel Agente

- [ ] Entradas aparecem com: timestamp, tool, resultado, decisão
- [ ] Nenhuma entrada mostra data inválida ou campos undefined

---

## 9. Resiliência — Bridge Offline

1. Para a bridge local
2. Com target=LOCAL, clica em "📷 Capturar tela"

- [ ] Toast de erro aparece: "Captura falhou: ..."
- [ ] Status muda para "bridge offline"
- [ ] UI não trava (sem alert bloqueante)

---

## 10. Resiliência — Target VPS

1. Com target=VPS, verifica seção de captura

- [ ] Botão "Capturar tela" está desabilitado
- [ ] Badge mostra "alvo: VPS"
- [ ] Nenhuma tentativa de conexão com bridge

---

## Resultado Final

| Área       | Status | Observação |
|------------|--------|------------|
| Backend API | ⬜ | |
| Bridge     | ⬜ | |
| Chat       | ⬜ | |
| Bridge UI  | ⬜ | |
| Captura    | ⬜ | |
| Agent Plan | ⬜ | |
| Aprovação  | ⬜ | |
| Auditoria  | ⬜ | |
| Resiliência| ⬜ | |

---

## Notas para nova entrega (Roadmap)

- [ ] Companion local mais robusto (Node/Electron) para live mouse/keyboard
- [ ] Stream contínuo de captura para observação em loop
- [ ] Fila de ações com feedback visual por ação
- [ ] Mouse/keyboard automation via bridge local
