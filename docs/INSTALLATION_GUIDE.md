# Luna Agent v2.0 - Guia de Instalação

## Pré-requisitos

- Python 3.11 ou superior
- Git
- Docker (opcional, para containerização)

## Instalação Rápida e Automática

Criamos scripts automáticos para facilitar a instalação. Eles verificam o Python, criam o ambiente virtual, instalam as dependências e criam as pastas necessárias.

### No Windows:
Basta dar um duplo clique no arquivo `setup.bat` ou executar no terminal:
```cmd
setup.bat
```

### No Linux / macOS:
Dê permissão de execução e rode o script:
```bash
chmod +x setup.sh
./setup.sh
```

### Instalação Universal (Python):
Se preferir usar o script Python multiplataforma:
```bash
python setup.py
```

## Configuração (Após a Instalação)

### 1. Configure as variáveis de ambiente
```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite o .env e adicione suas chaves de API
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=...
# GROK_API_KEY=...
```

### 2. Execute a Luna
```bash
# Ative o ambiente virtual primeiro
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Execute a Luna
python run_luna.py
```

## Instalação com Docker

### 1. Configure o .env
```bash
cp .env.example .env
# Edite com suas chaves de API
```

### 2. Execute com Docker Compose
```bash
docker-compose up -d --build
```

### 3. Acesse os logs
```bash
docker-compose logs -f luna-agent
```

## Solução de Problemas

### Erro: "ModuleNotFoundError: No module named 'app'"
- Certifique-se de estar no diretório raiz do projeto e com o ambiente virtual ativado (`source venv/bin/activate` ou `venv\Scripts\activate`)

### Erro: "OPENAI_API_KEY not found"
- Copie o arquivo `.env.example` para `.env`
- Adicione suas chaves de API no arquivo `.env`

### Erro: "Port 6379 already in use"
- Mude a porta no `docker-compose.yml`
- Ou pare o container Redis existente

## Suporte

Para dúvidas:
1. Verifique o README.md
2. Consulte os logs em `logs/luna.log`
