# Template: Testes Automatizados

## Unit (Vitest)
```bash
npm i -D vitest @testing-library/react @testing-library/jest-dom jsdom
```
Config em vitest.config.ts. Arquivos `*.test.ts(x)`.

## E2E (Playwright)
```bash
npm init playwright@latest
```
Padrao: testes em `e2e/*.spec.ts`. Rodar `npx playwright test`.

## Python (pytest)
```bash
pip install pytest pytest-asyncio httpx
```
Arquivos `test_*.py`. Fixtures em `conftest.py`.

## Regras
- Sempre rodar a suite localmente antes de entregar
- Cobrir happy path + pelo menos 2 edge cases por feature critica
- E2E cobre fluxos de usuario reais (login -> acao principal -> logout)
- Unit cobre logica de negocio e utils