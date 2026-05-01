# Template: Admin Dashboard (CRUD Complexo)

Use para painel admin, back-office, CRM, gestao de usuarios/pedidos/etc.

## Stack
- Next.js App Router + shadcn/ui
- `@tanstack/react-table` para tabelas avancadas
- `@tanstack/react-query` para cache + mutations
- `zod` + `react-hook-form` para forms
- `recharts` ou `tremor` para metricas no topo
- Better Auth para protecao de rotas admin

## Layout canonico
```
app/
  (admin)/
    layout.tsx           # sidebar + topbar + auth guard
    dashboard/page.tsx   # KPIs + graficos
    users/
      page.tsx            # tabela
      [id]/page.tsx       # detalhe + edicao
      new/page.tsx        # criar
    orders/page.tsx
    settings/page.tsx
```

## Sidebar admin
Secoes: Dashboard | Usuarios | Pedidos | Produtos | Relatorios | Logs | Settings
- Icones lucide com stroke 1.5
- Item ativo: bg-cyber-cyan/10 border-left-2 border-cyber-cyan
- Collapse em mobile (drawer)

## Tabela padrao (TanStack Table)
```tsx
const table = useReactTable({
  data, columns,
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  state: { sorting, columnFilters, rowSelection },
  ...
})
```

Features obrigatorias:
- Sorting clicavel no header
- Filter por coluna (DebouncedInput)
- Global search
- Paginacao (page size 10/25/50/100)
- Row selection (checkboxes)
- Bulk actions (delete, export, change status)
- Column visibility toggle
- Export CSV

## Form pattern (hook-form + zod)
```tsx
const schema = z.object({
  name: z.string().min(2),
  email: z.string().email(),
  role: z.enum(["admin", "user", "viewer"]),
})

const form = useForm<z.infer<typeof schema>>({
  resolver: zodResolver(schema),
  defaultValues: { ... },
})

<Form {...form}>
  <form onSubmit={form.handleSubmit(onSubmit)}>
    <FormField control={form.control} name="name" render={({ field }) => (
      <FormItem>
        <FormLabel>Nome</FormLabel>
        <FormControl><Input {...field} /></FormControl>
        <FormMessage />
      </FormItem>
    )} />
    ...
  </form>
</Form>
```

## KPI cards (dashboard home)
```tsx
<div className="grid grid-cols-1 md:grid-cols-4 gap-4">
  <KPICard title="MRR" value="$12,430" delta="+8.2%" trend="up" />
  <KPICard title="Active users" value="2,389" delta="+124" trend="up" />
  <KPICard title="Churn" value="2.1%" delta="-0.3pp" trend="down-good" />
  <KPICard title="NPS" value="52" delta="+3" trend="up" />
</div>
```

## Mutations com optimistic updates
```tsx
const mutation = useMutation({
  mutationFn: updateUser,
  onMutate: async (newData) => {
    await queryClient.cancelQueries(["users"])
    const prev = queryClient.getQueryData(["users"])
    queryClient.setQueryData(["users"], (old) => ({...old, ...newData}))
    return { prev }
  },
  onError: (err, _, ctx) => queryClient.setQueryData(["users"], ctx.prev),
  onSettled: () => queryClient.invalidateQueries(["users"]),
})
```

## Detalhe / edicao (pattern lateral drawer)
- Click em linha abre Sheet lateral com detalhe (evita full page reload)
- Tabs dentro do sheet: Info | Atividade | Notas | Audit log
- Botoes de acao no footer: Salvar | Deletar | Fechar

## Empty states sempre
- Tabela sem dados: ilustracao + "Nenhum usuario ainda" + CTA "Adicionar primeiro usuario"
- Filtro sem match: "Nenhum resultado para '<query>'" + botao limpar
- Erro de fetch: icone AlertCircle + mensagem + botao retry

## Regras de entrega
1. TanStack Table nao react-table v7 (deprecated)
2. Servidor: paginacao/filtro server-side quando > 100 rows
3. Loading states: skeleton rows, nao spinner
4. Audit log de acoes admin (quem fez o que e quando)
5. Role-based visibility (admin vs viewer)
6. Responsive: tabela vira cards em mobile
7. Dark mode obrigatorio (nosso tema E dark)