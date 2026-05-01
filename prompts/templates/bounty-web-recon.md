# Playbook: Bug Bounty Web - Reconhecimento

Use ANTES de qualquer teste ofensivo. Recon manda no bounty.

## Fluxo canonico
1. Scope check: `bounty_scope_check(target, in_scope, out_of_scope)` - NAO PROSSEGUIR se ABORT
2. Subdominios: `bounty_recon_subdomains(domain)` - subfinder com -all
3. Live hosts: `bounty_recon_live(subdomains, ports="80,443,8080,8443")` - httpx com tech-detect
4. Historico URLs: `bounty_recon_wayback(domain)` - gau/waybackurls
5. Crawl moderno: `bounty_crawl(url, depth=2, js=True)` - katana com JS
6. Fuzzing dirs: ffuf/feroxbuster em hosts interessantes com wordlist SecLists
7. Nuclei baseline: `bounty_scan_nuclei(live_hosts, severity="medium,high,critical")`

## Output esperado
```
recon_results/
  <domain>/
    subdomains.txt       # todos
    live.json            # httpx com status/title/tech
    wayback.txt          # URLs historicas
    crawl.txt            # katana
    nuclei.jsonl         # findings baseline
    scope.json           # in/out validation
```

## Priorizacao de targets (apos recon)
- Admin panels expostos (nuclei tag: panel, default-login)
- CVEs conhecidos (severity high+)
- APIs nao documentadas (paths /api/*, /v1/*, /graphql)
- Subdominios com tech stack desatualizado
- Hosts com CORS permissivo, headers de seguranca ausentes

## Anti-padroes
- Atacar sem scope_check (ILEGAL fora de bounty oficial)
- Rodar nuclei sem -severity (ruido massivo)
- Ignorar robots.txt/sitemap.xml antes de fuzz (pode indicar caminhos validos)
- Force brute DNS sem wordlist de qualidade (ruido e ban de IP)

## Quando pular recon profundo
- Scope bem definido e pequeno (<3 dominios)
- Foco em logica de negocio (ja sabe endpoints criticos)
- Pentest caixa-branca com docs