#!/bin/bash
# start_tunnel.sh — Inicia túnel SSH completo para Luna Agent
# Uso: ./scripts/start_tunnel.sh [usuario@vps] [porta_ssh]
#
# Abre:
#   -L 8000:localhost:8000  → acessa VPS UI localmente em http://localhost:8000
#   -R 8765:localhost:8765  → VPS acessa bridge local (reverse tunnel)
#
# Pré-requisitos:
#   - Bridge local rodando: cd /mnt/d/luna-agent && python -m uvicorn local_bridge:app --host 127.0.0.1 --port 8765
#   - Chave SSH configurada para o VPS

set -e

VPS="${1:-user@vps}"
SSH_PORT="${2:-22}"

echo "=== Luna Agent SSH Tunnel ==="
echo "VPS:        ${VPS}"
echo "SSH port:   ${SSH_PORT}"
echo ""
echo "Túneis:"
echo "  -L 8000:localhost:8000  → UI do VPS em http://localhost:8000"
echo "  -R 8765:localhost:8765  → Bridge local acessível no VPS"
echo ""
echo "Certifique-se que o bridge local está rodando em 127.0.0.1:8765"
echo "Pressione Ctrl+C para encerrar o túnel."
echo ""

ssh \
  -p "${SSH_PORT}" \
  -L 8000:localhost:8000 \
  -R 8765:localhost:8765 \
  -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  "${VPS}"
