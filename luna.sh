#!/bin/bash
LUNA_ROOT=$(dirname "$(readlink -f "$0")")
export PYTHONPATH="$LUNA_ROOT"
cd "$LUNA_ROOT"

# Localizar venv — prioridade: .venv_path (gerado pelo setup_wsl.sh) > venv local > luna-env local
if [ -f "$LUNA_ROOT/.venv_path" ]; then
    VENV_DIR=$(cat "$LUNA_ROOT/.venv_path")
elif [ -f "$LUNA_ROOT/venv/bin/activate" ]; then
    VENV_DIR="$LUNA_ROOT/venv"
elif [ -f "$LUNA_ROOT/luna-env/bin/activate" ]; then
    VENV_DIR="$LUNA_ROOT/luna-env"
else
    echo "⚠  Venv não encontrada. Execute primeiro:"
    echo "   chmod +x setup_wsl.sh && ./setup_wsl.sh"
    exit 1
fi

source "$VENV_DIR/bin/activate"
echo "[LUNA] Iniciando Luna Agent... (venv: $VENV_DIR)"
python run_luna.py
