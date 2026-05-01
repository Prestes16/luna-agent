"""
Luna Hunter-V2 Elite
=====================
Motor de auditoria de segurança Web3 de alta fidelidade para Bug Bounty.

Ecossistemas: Solana/Anchor, Solidity/EVM, Web3 APIs
Plataformas:  Immunefi, Code4rena, Firedancer

Módulos:
  laser_stream_service  — Monitoramento on-chain via Helius LaserStream
  audit_toolkit         — Orquestrador: Soteria, Anchor-Linter, Trident, Solana-Program-Test
  poc_generator         — Gerador de Exploit PoC (Rust + TypeScript)
  report_formatter      — Relatório no padrão Immunefi
  grains_manager        — Controle de créditos Luna Grains (custo de tokens)
  hunter_engine         — Orchestrador principal do fluxo Hunt
"""

from app.hunter.grains_manager import GrainsManager, get_grains_manager
from app.hunter.hunter_engine import HunterEngine, get_hunter_engine

__all__ = [
    "HunterEngine",
    "get_hunter_engine",
    "GrainsManager",
    "get_grains_manager",
]
