#!/usr/bin/env python3
"""
Luna Agent - Ponto de Entrada Principal
"""

import sys
from pathlib import Path

# Adicionar diretório atual ao PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

# Carregar variáveis de ambiente do .env ANTES de qualquer import da app
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from app.cli import main

if __name__ == "__main__":
    main()
