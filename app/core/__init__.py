"""
Luna Agent — Core Module
========================
Engines for advanced code understanding, project mapping, and security auditing.

Exports:
  ContextEngine  — 128k token project mapper with stack detection
  AuditEngine    — Multi-chain security vulnerability scanner
  AuditReport    — Structured audit result with markdown rendering
"""

from app.core.context_engine import ContextEngine, ProjectMap, CrossProjectAnalysis
from app.core.audit_engine import AuditEngine, AuditReport, Finding, Severity

__all__ = [
    "ContextEngine",
    "ProjectMap",
    "CrossProjectAnalysis",
    "AuditEngine",
    "AuditReport",
    "Finding",
    "Severity",
]
