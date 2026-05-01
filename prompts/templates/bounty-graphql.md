# Playbook: GraphQL Audit

## Primeiro passo
```
bounty_audit_graphql(endpoint="https://target/graphql")
```

## Vetores prioritarios

### 1. Introspeccao exposta em producao
Se `__schema` responde -> baixar schema completo e mapear mutations.
Se bloqueado, tentar via clairvoyance (field suggestions leak schema).

### 2. Field-level authorization ausente
Rodar mesma query logado e deslogado. Comparar campos retornados.
Exemplo: `user(id: "other") { email phone ssn }` funciona sem auth? -> High.

### 3. Mutation sensivel sem auth
Listar todas mutations: `updateUser`, `deletePost`, `adminCreate*`.
Tentar cada uma sem token ou com token de outro usuario.

### 4. Batch aliases DoS
```graphql
query {
  a1: expensiveQuery { ... }
  a2: expensiveQuery { ... }
  a3: expensiveQuery { ... }
  # x1000
}
```
Se rate limiter conta requests HTTP nao queries internas -> DoS.

### 5. Query depth/complexity
```graphql
query {
  user {
    friends { friends { friends { friends { ... } } } }
  }
}
```
Sem limite de profundidade -> DoS.

### 6. GraphQL CSRF via GET
Se mutations aceitas via GET com parametros -> CSRF trivial.

### 7. SQLi em resolvers
Parametros de argumentos podem passar direto para queries SQL. Testar:
```
{ users(filter: "admin' OR 1=1--") { id } }
```

### 8. NoSQLi / LDAPi
Operadores como `{ $gt: "" }` em JSON -> bypass auth.

### 9. Info disclosure em errors
Errors do GraphQL frequentemente vazam schema, paths internos, stack traces.

## Ferramentas
- **graphql-cop** - scanner automatico
- **clairvoyance** - schema inference quando introspection off
- **InQL (Burp ext)** - visual exploration
- **graphql-voyager** - viewer de schema baixado

## Tabela de severidade
| Cenario | Severity |
|---|---|
| Mutation admin sem auth | Critical |
| Field-level authz ausente (dados sensiveis) | High |
| SQLi em resolver | Critical |
| DoS via batch/depth | Medium-High |
| Introspection em producao | Low-Medium (mais info) |

## Mitigacoes a recomendar
- Desabilitar introspection em producao
- Query complexity limits (graphql-query-complexity)
- Depth limit (graphql-depth-limit)
- Persisted queries em producao
- Authz em RESOLVERS, nao apenas em queries top-level