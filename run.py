"""
Ponto de entrada da Luna — roda a partir da raiz do projeto.
Uso: python run.py
"""
import sys
import os

# Garante que D:\luna-agent esteja no path para imports absolutos funcionarem
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app  # noqa: E402
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("LUNA_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
