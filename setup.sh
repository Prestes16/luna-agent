#!/bin/bash

# Luna Agent v2.0 - Setup Script (Linux/macOS)
# Este script configura e executa a Luna Agent automaticamente

set -e

echo "🌙 Luna Agent v2.0 - Setup Automático"
echo "======================================"
echo ""

# Cores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Verificar Python
echo -e "${YELLOW}[1/5]${NC} Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 não encontrado!${NC}"
    echo "Por favor, instale Python 3.11 ou superior"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓ Python ${PYTHON_VERSION} encontrado${NC}"
echo ""

# Criar venv se não existir
echo -e "${YELLOW}[2/5]${NC} Configurando ambiente virtual..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Ambiente virtual criado${NC}"
else
    echo -e "${GREEN}✓ Ambiente virtual já existe${NC}"
fi
echo ""

# Ativar venv
echo -e "${YELLOW}[3/5]${NC} Ativando ambiente virtual..."
source venv/bin/activate
echo -e "${GREEN}✓ Ambiente virtual ativado${NC}"
echo ""

# Instalar dependências
echo -e "${YELLOW}[4/5]${NC} Instalando dependências..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
echo -e "${GREEN}✓ Dependências instaladas${NC}"
echo ""

# Criar diretórios necessários
echo -e "${YELLOW}[5/5]${NC} Criando diretórios..."
mkdir -p logs data workspaces
echo -e "${GREEN}✓ Diretórios criados${NC}"
echo ""

echo "======================================"
echo -e "${GREEN}✓ Setup concluído com sucesso!${NC}"
echo ""
echo "Para iniciar a Luna Agent, execute:"
echo -e "${YELLOW}source venv/bin/activate${NC}"
echo -e "${YELLOW}python run_luna.py${NC}"
echo ""
