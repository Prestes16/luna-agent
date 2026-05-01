#!/bin/bash
# Luna Agent v2.0 - Setup para WSL/Linux
set -e

LUNA_ROOT=$(dirname "$(readlink -f "$0")")
cd "$LUNA_ROOT"

# Venv fica no Linux filesystem para evitar erro de symlink no NTFS (/mnt/d/)
VENV_DIR="$HOME/.venvs/luna-agent"

echo ""
echo "🌙 Luna Agent v2.0 - Setup WSL/Linux"
echo "======================================"
echo ""

# 1. Verificar Python
echo "[1/5] Verificando Python..."
if ! command -v python3 &>/dev/null; then
    echo "✗ Python3 não encontrado! Instale com: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
PYVER=$(python3 --version)
echo "✓ $PYVER encontrado"
echo ""

# 2. Criar venv no filesystem Linux (evita erro de symlink no NTFS)
echo "[2/5] Configurando ambiente virtual..."
echo "   → Venv em: $VENV_DIR (Linux FS - evita erro NTFS)"
if [ ! -d "$VENV_DIR" ]; then
    mkdir -p "$HOME/.venvs"
    python3 -m venv "$VENV_DIR"
    echo "✓ Ambiente virtual criado"
else
    echo "✓ Ambiente virtual já existe"
fi
echo ""

# 3. Ativar venv e instalar dependências
echo "[3/5] Instalando dependências..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$LUNA_ROOT/requirements.txt"
echo "✓ Dependências instaladas"
echo ""

# 4. Criar diretórios necessários
echo "[4/5] Criando diretórios..."
mkdir -p "$LUNA_ROOT/logs"
mkdir -p "$LUNA_ROOT/data"
mkdir -p "$LUNA_ROOT/workspaces"
echo "✓ Diretórios criados"
echo ""

# 5. Verificar .env
echo "[5/5] Verificando .env..."
if [ ! -f "$LUNA_ROOT/.env" ]; then
    if [ -f "$LUNA_ROOT/.env.example" ]; then
        cp "$LUNA_ROOT/.env.example" "$LUNA_ROOT/.env"
        echo "⚠  .env criado a partir do .env.example — configure suas chaves de API!"
    else
        echo "⚠  Arquivo .env não encontrado. Crie um com OPENAI_API_KEY=sk-..."
    fi
else
    echo "✓ .env encontrado"
fi
echo ""

# Salvar o caminho da venv para o luna.sh usar
echo "$VENV_DIR" > "$LUNA_ROOT/.venv_path"

echo "======================================"
echo "✓ Setup concluído!"
echo ""
echo "Para executar a Luna:"
echo "  source $VENV_DIR/bin/activate"
echo "  cd /mnt/d/luna-agent && python run_luna.py"
echo ""
echo "Ou simplesmente:"
echo "  ./luna.sh"
echo "======================================"
