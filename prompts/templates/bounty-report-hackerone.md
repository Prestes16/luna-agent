# Template: Report HackerOne/Bugcrowd (Web)

## Formato obrigatorio

```markdown
## Summary
[Uma frase resumindo o bug e o impacto]

## Description
[Parágrafo explicando o bug, onde vive, por que acontece]

## Steps to Reproduce
1. Navegar para `https://target.com/path`
2. Logar como usuario A (credentials provistas ou criar conta)
3. Interceptar request `POST /api/xyz`
4. Alterar parametro `user_id` de A para B
5. Reenviar
6. Observar: dados de B retornados

## Proof of Concept
### Request
```http
POST /api/users/update HTTP/1.1
Host: target.com
Cookie: session=<A>
Content-Type: application/json

{"user_id": "<B>", "email": "attacker@evil.com"}
```

### Response
```http
HTTP/1.1 200 OK
{"success": true, "updated_user": "<B>"}
```

## Impact
[Explicar impacto tecnico E de negocio]
- Technical: IDOR permite UPDATE de qualquer conta
- Business: Account takeover em massa, reputation damage, LGPD/GDPR violation
- Affected users: TODOS os usuarios autenticados da plataforma
- Data exposed: emails, phones, payment tokens

## Supporting Material / References
- Screenshot: [attached]
- HAR file: [attached]
- Video PoC: [optional, for complex flows]
- OWASP ref: A01:2021 - Broken Access Control

## Suggested Fix
Validar autorizacao no servidor:
```js
if (req.user.id !== req.body.user_id && !req.user.isAdmin) {
  return res.status(403).json({ error: "forbidden" });
}
```

## Severity (CVSS 3.1)
Vector: AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:L
Score: 8.5 (High)
```

## Regras HackerOne/Bugcrowd
- NUNCA testar em conta de outro usuario (criar 2 contas proprias)
- Parar apos confirmar o bug - nao exfiltrar dados massivamente
- Respeitar rate limits do programa
- Reportar em ate 24h apos confirmacao

## Checklist
- [ ] Bug reproduzivel com steps claros?
- [ ] Scope: target esta in_scope do programa?
- [ ] Impact descrito em termos de negocio?
- [ ] PoC minima (menor request possivel)?
- [ ] CVSS calculado corretamente?
- [ ] Fix sugerido compila e resolve o root cause?
- [ ] Screenshots com info sensivel redacted (tokens, PII)?

## Anti-padroes
- Titulo generico ("XSS found")
- Impact vago ("could be exploited")
- Sem PoC ou PoC com alert(1) apenas
- Exagero de severidade
- Duplicatas (verificar hacktivity antes)