"""
Luna Agent - Context Engine (128k Project Mapping)
====================================================
Carregamento massivo e inteligente de projetos inteiros na janela de contexto.

Funcionalidades:
  - Lê múltiplos projetos simultaneamente (bags-shield-api + bags-shield-app2)
  - Prioriza arquivos por importância (entry points, configs, módulos core)
  - Detecta o tipo de stack por projeto (Python, TypeScript, Rust/Anchor, Solidity)
  - Constrói grafo de dependências entre arquivos e projetos
  - Identifica inconsistências entre Backend ↔ API (tipos, endpoints, modelos)
  - Comprime o contexto para caber na janela (128k tokens ≈ ~96k palavras)
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("luna.context_engine")

# ─── Tipos de stack detectáveis ───────────────────────────────────────────────

STACK_SIGNATURES: dict[str, list[str]] = {
    "solana_anchor": ["Anchor.toml", "programs/*/src/lib.rs", "Cargo.toml"],
    "solidity":      ["*.sol", "hardhat.config.*", "truffle-config.*", "foundry.toml"],
    "typescript":    ["tsconfig.json", "package.json", "*.ts", "*.tsx"],
    "python_fastapi":["main.py", "requirements.txt", "pyproject.toml", "app/main.py"],
    "python_generic":["*.py", "setup.py", "setup.cfg"],
    "rust_generic":  ["Cargo.toml", "src/main.rs", "src/lib.rs"],
}

# Arquivo de alta prioridade (sempre lidos primeiro)
PRIORITY_FILES = [
    # Configuração e entrada
    "main.py", "app.py", "server.py", "index.ts", "index.js",
    "app/main.py", "src/main.ts", "src/index.ts",
    "package.json", "Cargo.toml", "pyproject.toml", "requirements.txt",
    "Anchor.toml", "tsconfig.json", ".env.example",
    # Contratos / programas
    "programs/*/src/lib.rs", "contracts/*.sol",
    # Modelos e schemas
    "models.py", "schemas.py", "types.ts", "interfaces.ts",
    "app/models.py", "src/types/*.ts", "src/interfaces/*.ts",
    # Rotas e endpoints
    "routes.py", "router.py", "app/routes/*.py",
    "src/routes/*.ts", "src/api/*.ts", "src/controllers/*.ts",
    # Autenticação
    "auth.py", "middleware.py", "src/middleware/*.ts",
]

# Extensões ignoradas completamente
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".map", ".lock", ".bin", ".exe", ".dll", ".so",
    ".pyc", ".pyo", ".egg-info", ".dist-info",
}

# Diretórios ignorados
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target/debug", "target/release",
    ".pytest_cache", "coverage", ".mypy_cache",
}

# Tokens aproximados por caractere (estimativa conservadora)
CHARS_PER_TOKEN = 3.5


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class FileEntry:
    path: str            # caminho relativo ao project_root
    abs_path: str        # caminho absoluto
    content: str
    size_bytes: int
    language: str        # "python" | "typescript" | "rust" | "solidity" | "toml" | etc.
    priority: int        # 0=crítico, 1=alto, 2=médio, 3=baixo
    tokens_est: int      # estimativa de tokens


@dataclass
class ProjectMap:
    root: str
    name: str
    stack: str
    files: list[FileEntry] = field(default_factory=list)
    endpoints: list[dict]  = field(default_factory=list)   # {method, path, file, line}
    models: list[dict]     = field(default_factory=list)   # {name, fields, file, line}
    exports: list[str]     = field(default_factory=list)   # tipos/funções exportadas (TS)
    total_tokens: int      = 0

    def summary(self) -> str:
        return (
            f"Project: {self.name} | Stack: {self.stack} | "
            f"Files: {len(self.files)} | Tokens: {self.total_tokens:,} | "
            f"Endpoints: {len(self.endpoints)} | Models: {len(self.models)}"
        )


@dataclass
class CrossProjectAnalysis:
    projects: list[ProjectMap]
    inconsistencies: list[dict]   # {type, description, locations}
    shared_types: list[str]
    missing_in_api: list[str]     # endpoints no backend sem correspondência na API
    missing_in_backend: list[str] # tipos no frontend sem schema no backend
    dependency_graph: dict        # {file: [files_it_imports]}
    context_budget_used: int      # tokens totais usados
    context_budget_max: int


# ─── Utilitários ──────────────────────────────────────────────────────────────

def _detect_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript",
        ".rs": "rust", ".sol": "solidity",
        ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
        ".json": "json", ".md": "markdown",
        ".sh": "bash", ".env": "env",
    }.get(ext, "text")


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def _is_priority(rel_path: str) -> int:
    """Retorna prioridade 0-3 para um arquivo."""
    name = Path(rel_path).name
    parts = rel_path.replace("\\", "/")

    # Prioridade 0: arquivos críticos de entrada
    critical = {"main.py", "app.py", "server.py", "index.ts", "index.js",
                 "lib.rs", "Cargo.toml", "Anchor.toml", "package.json",
                 "pyproject.toml", "requirements.txt", "tsconfig.json"}
    if name in critical:
        return 0

    # Prioridade 1: modelos, schemas, rotas
    p1_patterns = ["model", "schema", "route", "router", "endpoint",
                    "controller", "interface", "type", "auth", "middleware"]
    if any(p in name.lower() for p in p1_patterns):
        return 1

    # Prioridade 2: código-fonte principal
    if any(seg in parts for seg in ["src/", "app/", "programs/", "contracts/"]):
        return 2

    return 3   # baixa prioridade (configs, testes, docs)


# ─── Extratores de metadados ──────────────────────────────────────────────────

def _extract_python_endpoints(content: str, rel_path: str) -> list[dict]:
    """Extrai endpoints FastAPI/Flask de código Python."""
    endpoints = []
    for m in re.finditer(
        r'@(?:app|router|blueprint)\.(get|post|put|patch|delete|options)\s*\(\s*["\']([^"\']+)["\']',
        content, re.IGNORECASE
    ):
        endpoints.append({
            "method": m.group(1).upper(),
            "path":   m.group(2),
            "file":   rel_path,
            "line":   content[:m.start()].count("\n") + 1,
        })
    return endpoints


def _extract_ts_endpoints(content: str, rel_path: str) -> list[dict]:
    """Extrai rotas Express/Fastify/NestJS de TypeScript."""
    endpoints = []
    for m in re.finditer(
        r'\.(get|post|put|patch|delete)\s*\(\s*["\`]([^"\`]+)["\`]',
        content, re.IGNORECASE
    ):
        endpoints.append({
            "method": m.group(1).upper(),
            "path":   m.group(2),
            "file":   rel_path,
            "line":   content[:m.start()].count("\n") + 1,
        })
    # NestJS decorators
    for m in re.finditer(
        r'@(Get|Post|Put|Patch|Delete)\s*\(\s*["\`]([^"\`]*)["\`]',
        content
    ):
        endpoints.append({
            "method": m.group(1).upper(),
            "path":   m.group(2),
            "file":   rel_path,
            "line":   content[:m.start()].count("\n") + 1,
        })
    return endpoints


def _extract_python_models(content: str, rel_path: str) -> list[dict]:
    """Extrai modelos Pydantic/SQLAlchemy."""
    models = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [b.id if isinstance(b, ast.Name) else
                         (b.attr if isinstance(b, ast.Attribute) else "")
                         for b in node.bases]
                if any(b in ("BaseModel", "Base", "Model", "Schema") for b in bases):
                    fields = [
                        n.targets[0].id if isinstance(n, ast.Assign)
                        and isinstance(n.targets[0], ast.Name) else
                        (n.target.id if isinstance(n, ast.AnnAssign)
                         and isinstance(n.target, ast.Name) else None)
                        for n in node.body
                    ]
                    models.append({
                        "name":   node.name,
                        "fields": [f for f in fields if f and not f.startswith("_")],
                        "file":   rel_path,
                        "line":   node.lineno,
                    })
    except Exception:
        pass
    return models


def _extract_ts_interfaces(content: str, rel_path: str) -> list[dict]:
    """Extrai interfaces e types TypeScript."""
    models = []
    for m in re.finditer(
        r'(?:export\s+)?(?:interface|type)\s+(\w+)\s*(?:<[^>]*>)?\s*[={]([^}]+)}',
        content, re.DOTALL
    ):
        name = m.group(1)
        body = m.group(2)
        fields = re.findall(r'(\w+)\s*[?:]', body)
        models.append({
            "name":   name,
            "fields": fields[:20],
            "file":   rel_path,
            "line":   content[:m.start()].count("\n") + 1,
        })
    return models


def _extract_ts_exports(content: str) -> list[str]:
    """Extrai nomes exportados de um arquivo TypeScript."""
    exports = []
    for m in re.finditer(r'export\s+(?:default\s+)?(?:interface|type|class|function|const|enum)\s+(\w+)', content):
        exports.append(m.group(1))
    return exports


# ─── Motor principal ──────────────────────────────────────────────────────────

class ContextEngine:
    """
    Carrega múltiplos projetos em memória, respeitando o budget de tokens.

    Exemplo:
        engine = ContextEngine(max_tokens=120_000)
        analysis = engine.load_projects([
            "/mnt/c/Dev/bags-shield-api",
            "/mnt/c/Dev/bags-shield-app2",
        ])
        prompt_context = engine.build_prompt_context(analysis)
    """

    def __init__(self, max_tokens: int = 120_000) -> None:
        self.max_tokens = max_tokens
        self._budget_used = 0

    # ── Stack detection ───────────────────────────────────────────────────

    def detect_stack(self, root: Path) -> str:
        files = {f.name for f in root.rglob("*") if f.is_file()}
        dirs  = {d.name for d in root.rglob("*") if d.is_dir()}

        if "Anchor.toml" in files or "programs" in dirs:
            return "solana_anchor"
        if any(f.endswith(".sol") for f in files):
            return "solidity"
        if "tsconfig.json" in files or "package.json" in files:
            # Pode ser TS puro ou TS + Python (monorepo)
            if "requirements.txt" in files or "pyproject.toml" in files:
                return "typescript+python"
            return "typescript"
        if "requirements.txt" in files or "pyproject.toml" in files:
            return "python_fastapi"
        if "Cargo.toml" in files:
            return "rust_generic"
        return "unknown"

    # ── Leitura de arquivos ───────────────────────────────────────────────

    def _iter_files(self, root: Path) -> Iterator[Path]:
        """Itera arquivos em ordem de prioridade."""
        all_files = []
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            # Pular diretórios ignorados
            if any(skip in f.parts for skip in SKIP_DIRS):
                continue
            # Pular extensões ignoradas
            if f.suffix.lower() in SKIP_EXTENSIONS:
                continue
            # Pular arquivos muito grandes (>500KB)
            try:
                if f.stat().st_size > 500_000:
                    continue
            except OSError:
                continue
            rel = str(f.relative_to(root))
            prio = _is_priority(rel)
            all_files.append((prio, f.name, f))

        all_files.sort(key=lambda x: (x[0], x[1]))
        for _, _, path in all_files:
            yield path

    def _read_file(self, path: Path, root: Path) -> FileEntry | None:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"[ctx] Não foi possível ler {path}: {e}")
            return None

        rel = str(path.relative_to(root))
        tokens = _estimate_tokens(content)
        lang   = _detect_language(str(path))
        prio   = _is_priority(rel)

        return FileEntry(
            path=rel,
            abs_path=str(path),
            content=content,
            size_bytes=path.stat().st_size,
            language=lang,
            priority=prio,
            tokens_est=tokens,
        )

    # ── Carregamento de projeto ───────────────────────────────────────────

    def load_project(self, project_path: str, budget_remaining: int) -> ProjectMap:
        root  = Path(project_path).resolve()
        name  = root.name
        stack = self.detect_stack(root)
        pmap  = ProjectMap(root=str(root), name=name, stack=stack)

        if not root.exists():
            logger.warning(f"[ctx] Projeto não encontrado: {project_path}")
            return pmap

        logger.info(f"[ctx] Carregando {name} (stack={stack}, budget={budget_remaining:,} tokens)")

        for fpath in self._iter_files(root):
            if budget_remaining <= 0:
                logger.info(f"[ctx] Budget esgotado após {len(pmap.files)} arquivos de {name}")
                break

            entry = self._read_file(fpath, root)
            if entry is None:
                continue

            # Truncar arquivo se muito grande mas preservar prioridade 0/1
            if entry.tokens_est > budget_remaining:
                if entry.priority <= 1:
                    # Truncar mas incluir
                    max_chars = int(budget_remaining * CHARS_PER_TOKEN)
                    entry.content = entry.content[:max_chars] + f"\n...[TRUNCADO — {entry.size_bytes} bytes totais]"
                    entry.tokens_est = budget_remaining
                else:
                    continue   # pular arquivo secundário muito grande

            # Extrair metadados
            if entry.language == "python":
                pmap.endpoints.extend(_extract_python_endpoints(entry.content, entry.path))
                pmap.models.extend(_extract_python_models(entry.content, entry.path))
            elif entry.language == "typescript":
                pmap.endpoints.extend(_extract_ts_endpoints(entry.content, entry.path))
                pmap.models.extend(_extract_ts_interfaces(entry.content, entry.path))
                pmap.exports.extend(_extract_ts_exports(entry.content))

            pmap.files.append(entry)
            pmap.total_tokens += entry.tokens_est
            budget_remaining  -= entry.tokens_est

        logger.info(
            f"[ctx] {name}: {len(pmap.files)} arquivos, "
            f"{pmap.total_tokens:,} tokens, "
            f"{len(pmap.endpoints)} endpoints, "
            f"{len(pmap.models)} modelos"
        )
        return pmap

    # ── Análise cross-projeto ─────────────────────────────────────────────

    def _find_inconsistencies(self, projects: list[ProjectMap]) -> list[dict]:
        """Detecta inconsistências entre projetos (backend ↔ frontend/api)."""
        issues = []

        if len(projects) < 2:
            return issues

        # Coletar endpoints e modelos de cada projeto
        backend_eps   = {f"{e['method']} {e['path']}": e for p in projects
                         if "python" in p.stack or "fastapi" in p.stack
                         for e in p.endpoints}
        frontend_eps  = {f"{e['method']} {e['path']}": e for p in projects
                         if "typescript" in p.stack
                         for e in p.endpoints}

        backend_models   = {m["name"]: m for p in projects
                            if "python" in p.stack for m in p.models}
        frontend_models  = {m["name"]: m for p in projects
                            if "typescript" in p.stack for m in p.models}

        # Endpoints no frontend que não existem no backend
        for ep_key, ep in frontend_eps.items():
            if ep_key not in backend_eps:
                issues.append({
                    "type":        "missing_backend_endpoint",
                    "description": f"Frontend chama {ep_key} mas endpoint não encontrado no backend",
                    "locations":   [ep["file"]],
                    "severity":    "high",
                })

        # Modelos com campos divergentes
        common_models = set(backend_models) & set(frontend_models)
        for name in common_models:
            bm = set(backend_models[name]["fields"])
            fm = set(frontend_models[name]["fields"])
            only_backend  = bm - fm
            only_frontend = fm - bm
            if only_backend or only_frontend:
                issues.append({
                    "type":        "model_field_mismatch",
                    "description": (
                        f"Modelo '{name}' diverge: "
                        f"só no backend: {only_backend}, "
                        f"só no frontend: {only_frontend}"
                    ),
                    "locations":   [
                        backend_models[name]["file"],
                        frontend_models[name]["file"],
                    ],
                    "severity":    "medium",
                })

        return issues

    def _build_dep_graph(self, projects: list[ProjectMap]) -> dict[str, list[str]]:
        """Constrói grafo de importações entre arquivos."""
        graph: dict[str, list[str]] = {}

        for pmap in projects:
            for entry in pmap.files:
                deps = []
                if entry.language == "python":
                    for m in re.finditer(r'^(?:from|import)\s+([\w\.]+)', entry.content, re.MULTILINE):
                        deps.append(m.group(1))
                elif entry.language == "typescript":
                    for m in re.finditer(r"(?:import|from)\s+['\"]([^'\"]+)['\"]", entry.content):
                        deps.append(m.group(1))
                full_key = f"{pmap.name}/{entry.path}"
                graph[full_key] = deps

        return graph

    # ── API pública ───────────────────────────────────────────────────────

    def load_projects(self, project_paths: list[str]) -> CrossProjectAnalysis:
        """
        Carrega múltiplos projetos respeitando o budget total de tokens.
        Distribui o budget igualmente entre os projetos.
        """
        n = max(1, len(project_paths))
        per_project = self.max_tokens // n
        projects = []

        for path in project_paths:
            pmap = self.load_project(path, per_project)
            projects.append(pmap)

        total_used = sum(p.total_tokens for p in projects)
        inconsistencies = self._find_inconsistencies(projects)
        dep_graph = self._build_dep_graph(projects)

        # Tipos compartilhados
        all_model_names = {}
        for p in projects:
            for m in p.models:
                all_model_names.setdefault(m["name"], []).append(p.name)
        shared = [name for name, projs in all_model_names.items() if len(projs) > 1]

        # Endpoints sem correspondência
        backend_paths  = {e["path"] for p in projects if "python" in p.stack for e in p.endpoints}
        frontend_paths = {e["path"] for p in projects if "typescript" in p.stack for e in p.endpoints}
        missing_api     = list(backend_paths - frontend_paths)
        missing_backend = list(frontend_paths - backend_paths)

        analysis = CrossProjectAnalysis(
            projects=projects,
            inconsistencies=inconsistencies,
            shared_types=shared,
            missing_in_api=missing_api,
            missing_in_backend=missing_backend,
            dependency_graph=dep_graph,
            context_budget_used=total_used,
            context_budget_max=self.max_tokens,
        )

        logger.info(
            f"[ctx] Análise completa: {len(projects)} projetos, "
            f"{total_used:,}/{self.max_tokens:,} tokens usados, "
            f"{len(inconsistencies)} inconsistências encontradas"
        )
        return analysis

    # ── Construção do prompt ──────────────────────────────────────────────

    def build_prompt_context(self, analysis: CrossProjectAnalysis) -> str:
        """
        Serializa a análise em texto formatado para injeção no LLM.
        Estrutura:
          [PROJECT: name] stack=... files=... endpoints=... models=...
          [FILE: path] (language)
          <conteúdo>
          [INCONSISTENCIES]
          ...
        """
        lines: list[str] = []

        for pmap in analysis.projects:
            lines.append(f"\n{'='*60}")
            lines.append(f"[PROJECT: {pmap.name}]")
            lines.append(f"Stack: {pmap.stack} | Root: {pmap.root}")
            lines.append(f"Files: {len(pmap.files)} | Tokens: {pmap.total_tokens:,}")

            if pmap.endpoints:
                lines.append(f"\nEndpoints ({len(pmap.endpoints)}):")
                for ep in pmap.endpoints[:30]:
                    lines.append(f"  {ep['method']:6} {ep['path']:40} [{ep['file']}:{ep['line']}]")

            if pmap.models:
                lines.append(f"\nModelos/Interfaces ({len(pmap.models)}):")
                for m in pmap.models[:20]:
                    fields_str = ", ".join(m["fields"][:8])
                    lines.append(f"  {m['name']} ({fields_str}) [{m['file']}:{m['line']}]")

            lines.append("\n" + "-"*60 + " ARQUIVOS " + "-"*60)
            for entry in pmap.files:
                lines.append(f"\n[FILE: {pmap.name}/{entry.path}] ({entry.language})")
                lines.append(entry.content)

        if analysis.inconsistencies:
            lines.append(f"\n{'='*60}")
            lines.append(f"[INCONSISTÊNCIAS DETECTADAS: {len(analysis.inconsistencies)}]")
            for issue in analysis.inconsistencies:
                sev = issue.get("severity", "?").upper()
                lines.append(f"\n[{sev}] {issue['type']}")
                lines.append(f"  {issue['description']}")
                for loc in issue.get("locations", []):
                    lines.append(f"  → {loc}")

        if analysis.shared_types:
            lines.append(f"\n[TIPOS COMPARTILHADOS: {', '.join(analysis.shared_types[:20])}]")

        if analysis.missing_in_backend:
            lines.append(f"\n[ENDPOINTS NO FRONTEND SEM BACKEND: {', '.join(analysis.missing_in_backend[:10])}]")

        lines.append(f"\n{'='*60}")
        lines.append(f"[CONTEXTO: {analysis.context_budget_used:,}/{analysis.context_budget_max:,} tokens]")

        return "\n".join(lines)

    def summary_report(self, analysis: CrossProjectAnalysis) -> str:
        """Relatório resumido para exibir no terminal antes de enviar ao LLM."""
        lines = ["📦 CONTEXTO CARREGADO:"]
        for p in analysis.projects:
            lines.append(f"  {p.name}: {len(p.files)} arquivos | {p.total_tokens:,} tokens | stack={p.stack}")
        lines.append(f"  Budget: {analysis.context_budget_used:,}/{analysis.context_budget_max:,} tokens")
        if analysis.inconsistencies:
            highs = sum(1 for i in analysis.inconsistencies if i.get("severity") == "high")
            lines.append(f"  ⚠️  {len(analysis.inconsistencies)} inconsistências ({highs} high)")
        if analysis.shared_types:
            lines.append(f"  🔗 Tipos compartilhados: {', '.join(analysis.shared_types[:5])}")
        return "\n".join(lines)


# ─── Singleton global ─────────────────────────────────────────────────────────

def get_context_engine(max_tokens: int = 120_000) -> ContextEngine:
    return ContextEngine(max_tokens=max_tokens)
