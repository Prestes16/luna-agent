# Luna Cyber 🌙

**Local AI Copilot para cybersecurity e desenvolvimento**

Luna Desktop é uma aplicação multiplataforma de alta performance que traz toda a inteligência e capacidades do agente Luna para seu computador. Especializada em programação de grande porte, análise de segurança, criptografia e blockchain Solana.

## 🌟 Características Principais

### 🧠 Inteligência Local
- **Ollama local**: `luna-cyber-fast` como modelo principal e `qwen3.5:4b` como fallback
- **Copiloto supervisionado**: o operador mantém controle sobre comandos e ações
- **Memória Persistente**: STM (curto prazo) + LTM (longo prazo) com busca semântica
- **Interpretação Avançada**: Compreensão profunda de prompts complexos

### 💻 Análise de Código
- **Análise de Complexidade**: Métricas detalhadas de código
- **Detecção de Problemas**: Identifica bugs, anti-patterns e oportunidades de otimização
- **Análise de Projetos**: Avalia estrutura e qualidade de todo o projeto
- **Suporte Multi-Linguagem**: Python, JavaScript, TypeScript, Java, C++, Go, Rust

### 🔒 Segurança e Hacking Ético
- **Scanner de Vulnerabilidades**: Detecta SQL injection, XSS, hardcoded secrets, etc.
- **Análise Criptográfica**: Avalia força e implementação de criptografia
- **Teste de Penetração**: Ferramentas para teste de segurança
- **Conformidade**: Verifica OWASP, CWE e outras normas

### ⛓️ Blockchain Solana
- **Carteira Integrada**: Gerenciamento de carteira Solana nativa
- **Transações**: Criar e monitorar transações na rede Solana
- **Smart Contracts**: Análise e deploy de programas Solana
- **DeFi Tools**: Ferramentas para interação com protocolos DeFi

### 🎨 Interface Moderna
- **Layout ajustável**: sidebar persistente e painel de execução redimensionável
- **Design responsivo**: painel direito recolhido automaticamente em janelas estreitas sem perder a preferência
- **Tema dark-first**: identidade visual lunar/cyber otimizada para desktop
- **Gráficos em Tempo Real**: Visualizações de dados e métricas
- **Terminal Integrado**: Acesso a comandos avançados

## 🚀 Instalação Rápida

### Pré-requisitos
- Node.js 20+ e npm 11+
- Python 3.11+
- Git

### Passos de Instalação

1. **Clone o repositório**
```bash
cd D:\luna-agent\luna-desktop
```

2. **Instale dependências do frontend**
```bash
npm install
```

3. **Instale dependências do backend**
```bash
cd backend
pip install -r requirements.txt
cd ..
```

4. **Confira a configuração local**
```bash
cp .env.example .env
# Nenhuma chave cloud é necessária
```

5. **Inicie a aplicação**
```bash
npm run dev
```

Isso iniciará:
- Frontend React em http://localhost:5173
- Backend FastAPI em http://localhost:8000
- Aplicação Electron

## 📦 Estrutura do Projeto

```
luna-desktop/
├── src/                          # Frontend React + TypeScript
│   ├── components/              # Componentes reutilizáveis
│   ├── pages/                   # Páginas da aplicação
│   ├── services/                # Serviços de API
│   ├── store/                   # Gerenciamento de estado (Zustand)
│   ├── types/                   # Tipos TypeScript
│   ├── hooks/                   # Hooks customizados
│   └── App.tsx                  # Componente raiz
├── backend/                      # Backend Python + FastAPI
│   ├── app/
│   │   ├── luna_engine.py       # Cérebro da Luna
│   │   ├── models.py            # Modelos Pydantic
│   │   └── __init__.py
│   ├── services/
│   │   ├── code_analyzer.py     # Análise de código
│   │   ├── security_scanner.py  # Scanner de segurança
│   │   ├── blockchain_service.py # Integração Solana
│   │   └── __init__.py
│   ├── main.py                  # Servidor FastAPI
│   └── requirements.txt          # Dependências Python
├── public/                       # Assets estáticos
├── config/                       # Configurações
├── package.json                  # Dependências npm
├── tsconfig.json                # Configuração TypeScript
├── vite.config.ts               # Configuração Vite
└── README.md                     # Este arquivo
```

## 🎯 Páginas Principais

### Dashboard
Visão geral do sistema com métricas em tempo real, gráficos de uso e atividades recentes.

### Chat
Interface de conversa com streaming local, histórico, memória, workspace e imagens. O autoscroll acompanha a resposta somente quando a leitura está no final.

### Projects
Projetos locais com mensagens, fatos e contexto persistidos em JSON UTF-8 por escrita atômica. O diretório vem de `LUNA_PROJECTS_DIR` e usa `D:\LunaCyber\projects` como fallback.

### Code Analyzer
Análise avançada de código com detecção de complexidade, problemas e recomendações.

### Security
Scanner de segurança, verificação de vulnerabilidades e status de ameaças.

### Blockchain
Gerenciamento de carteira Solana, transações e interação com smart contracts.

### Settings
Configuração do Ollama, modelos locais, workspace, módulos e segurança.

## 🦙 Configuração local

O frontend não exige conta ou chave de provedor. As configurações principais são:

```env
VITE_API_URL=http://localhost:8000
OLLAMA_BASE_URL=http://localhost:11434/v1
LUNA_DEFAULT_MODEL=luna-cyber-fast
LUNA_PROJECTS_DIR=D:\LunaCyber\projects
ZERO_CLOUD_MODE=true
VITE_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
```

## 🛠️ Desenvolvimento

### Scripts Disponíveis

```bash
# Desenvolvimento
npm run dev              # Inicia frontend + backend

# Build
npm run build           # Build para produção
npm run react-build     # Build apenas frontend

# Packaging
npm run dist            # Cria instalador para Windows
npm run dist-win        # Instalador Windows
npm run dist-mac        # Instalador macOS
npm run dist-linux      # Instalador Linux

# Testes
npm run test:run        # Executa testes do frontend uma vez
npm run typecheck       # Valida TypeScript sem gerar arquivos
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Linting
npm run lint            # Verifica código
```

### Desenvolvimento Local

Terminal 1 - Frontend:
```bash
npm run react-dev
```

Terminal 2 - Backend:
```bash
cd backend
python main.py
```

Terminal 3 - Electron:
```bash
npm run electron
```

## 🔐 Segurança

Luna Desktop implementa múltiplas camadas de segurança:

- **Isolamento de Contexto**: Preload scripts e context isolation no Electron
- **Criptografia E2E**: Comunicação criptografada entre frontend e backend
- **Validação de Entrada**: Sanitização de todos os inputs
- **Sandboxing**: Execução segura de código analisado
- **Auditoria**: Log completo de todas as ações

## 📊 Performance

- **Startup Time**: < 3 segundos
- **Memory Usage**: ~200MB (base)
- **Response Time**: < 1 segundo (média)
- **Token Processing**: 1000+ tokens/segundo

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor:

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📝 Licença

Este projeto está sob licença MIT. Veja o arquivo LICENSE para detalhes.

## 📞 Suporte

Para dúvidas ou problemas:

1. Verifique a documentação
2. Consulte os logs em `logs/`
3. Abra uma issue no GitHub
4. Entre em contato com o suporte

## 🎓 Recursos Adicionais

- [Documentação Completa](./docs/README.md)
- [Guia de Desenvolvimento](./docs/DEVELOPMENT.md)
- [API Reference](./docs/API.md)
- [Segurança](./docs/SECURITY.md)

---

**Construído com ❤️ para desenvolvedores que exigem excelência**

Versão: 3.0.0 | Data: Abril 2026 | Status: ✅ Pronto para Produção
