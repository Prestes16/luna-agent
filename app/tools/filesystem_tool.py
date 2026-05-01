"""
Luna Agent - Filesystem Tool
Acesso controlado ao sistema de arquivos com política de segurança por diretórios.
"""

from __future__ import annotations

import os
import re as _re
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("luna.tools.filesystem")


class FilesystemTool:
    """
    Ferramenta de acesso ao filesystem com whitelist de diretórios.
    Toda operação é validada contra os diretórios permitidos antes de executar.
    """

    def __init__(self, allowed_dirs: list[str]):
        self.allowed_dirs = [Path(d).resolve() for d in allowed_dirs if d]
        logger.info(f"FilesystemTool inicializado. Dirs permitidos: {self.allowed_dirs}")

    # ── Validação ─────────────────────────────────────────────────────────

    def is_allowed(self, path: str | Path) -> bool:
        """Verifica se o caminho está dentro de um diretório permitido."""
        try:
            resolved = Path(path).resolve()
            return any(
                resolved == allowed or allowed in resolved.parents
                for allowed in self.allowed_dirs
            )
        except Exception:
            return False

    def _check(self, path: str | Path) -> Path:
        """Resolve e valida o caminho. Lança exceção se não permitido."""
        p = Path(path).resolve()
        if not self.is_allowed(p):
            raise PermissionError(
                f"Acesso negado: '{p}' fora dos diretórios permitidos.\n"
                f"Permitidos: {[str(d) for d in self.allowed_dirs]}"
            )
        return p

    # ── Leitura ───────────────────────────────────────────────────────────

    def list_dir(self, path: str, show_hidden: bool = False) -> dict:
        """Lista o conteúdo de um diretório."""
        p = self._check(path)
        if not p.exists():
            return {"error": f"Caminho não existe: {p}"}
        if not p.is_dir():
            return {"error": f"Não é um diretório: {p}"}

        entries = []
        try:
            items = sorted(p.iterdir())
        except OSError:
            items = []
        for item in items:
            if not show_hidden and item.name.startswith("."):
                continue
            try:
                is_dir  = item.is_dir()
                is_file = item.is_file()
                size    = item.stat().st_size if is_file else None
            except OSError:
                is_dir, is_file, size = False, False, None
            entries.append({
                "name": item.name,
                "type": "dir" if is_dir else "file",
                "size": size,
            })

        return {"path": str(p), "entries": entries, "count": len(entries)}

    def read_file(self, path: str, max_chars: int = 4000) -> dict:
        """Lê o conteúdo de um arquivo."""
        p = self._check(path)
        if not p.exists():
            return {"error": f"Arquivo não existe: {p}"}
        if not p.is_file():
            return {"error": f"Não é um arquivo: {p}"}

        size = p.stat().st_size
        if size > 1_000_000:
            return {"error": f"Arquivo muito grande ({size} bytes). Use um editor externo."}

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            truncated = len(content) > max_chars
            return {
                "path": str(p),
                "content": content[:max_chars],
                "truncated": truncated,
                "size": size,
            }
        except Exception as e:
            return {"error": f"Erro ao ler arquivo: {e}"}

    def search_files(self, path: str, pattern: str, max_results: int = 50) -> dict:
        """Busca arquivos por padrão glob dentro de um diretório."""
        p = self._check(path)
        if not p.is_dir():
            return {"error": f"Não é um diretório: {p}"}

        results = []
        try:
            _matches = list(p.rglob(pattern))
        except OSError:
            _matches = []
        for match in sorted(_matches)[:max_results]:
            try:
                if self.is_allowed(match):
                    results.append(str(match))
            except OSError:
                pass

        return {"pattern": pattern, "root": str(p), "matches": results, "count": len(results)}

    def grep_file(self, path: str, query: str, max_lines: int = 100) -> dict:
        """Busca texto dentro de um arquivo."""
        p = self._check(path)
        result = self.read_file(str(p))
        if "error" in result:
            return result

        matches = []
        for i, line in enumerate(result["content"].splitlines(), 1):
            if query.lower() in line.lower():
                matches.append({"line": i, "content": line})
            if len(matches) >= max_lines:
                break

        return {"path": str(p), "query": query, "matches": matches, "count": len(matches)}

    # ── Escrita ───────────────────────────────────────────────────────────

    def write_file(self, path: str, content: str) -> dict:
        """Escreve conteúdo em um arquivo (cria ou sobrescreve).
        Se o arquivo já existir, cria um backup .bak antes de sobrescrever.
        """
        p = self._check(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            # Backup automático se o arquivo já existir
            backed_up = False
            if p.exists():
                bak = p.with_suffix(p.suffix + ".bak")
                try:
                    bak.write_bytes(p.read_bytes())
                    backed_up = True
                except Exception as bak_err:
                    logger.warning(f"write_file: não foi possível criar backup de {p}: {bak_err}")
            p.write_text(content, encoding="utf-8")
            return {
                "path": str(p),
                "bytes_written": len(content.encode("utf-8")),
                "backup": str(p.with_suffix(p.suffix + ".bak")) if backed_up else None,
                "ok": True,
            }
        except Exception as e:
            return {"error": f"Erro ao escrever arquivo: {e}"}

    def patch_file(self, path: str, old: str, new: str) -> dict:
        """Substitui uma ocorrência de texto em um arquivo.
        Cria backup .bak antes de modificar.
        """
        p = self._check(path)
        result = self.read_file(str(p), max_chars=500_000)
        if "error" in result:
            return result

        content = result["content"]
        if old not in content:
            return {"error": f"Texto não encontrado no arquivo: '{old[:80]}...'"}

        # Backup antes de modificar
        bak = p.with_suffix(p.suffix + ".bak")
        try:
            bak.write_bytes(p.read_bytes())
        except Exception as bak_err:
            logger.warning(f"patch_file: não foi possível criar backup de {p}: {bak_err}")

        updated = content.replace(old, new, 1)
        write_result = self.write_file(str(p), updated)
        if "error" in write_result:
            return write_result

        return {"path": str(p), "ok": True, "replaced": True, "backup": str(bak)}

    def create_dir(self, path: str) -> dict:
        """Cria um diretório (e pais se necessário)."""
        p = self._check(path)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return {"path": str(p), "ok": True}
        except Exception as e:
            return {"error": f"Erro ao criar diretório: {e}"}

    def read_many(self, paths: list[str], max_chars_each: int = 1500) -> dict:
        """Lê múltiplos arquivos de uma vez. Limita a 4 arquivos por chamada para evitar rate limit."""
        MAX_FILES = 4
        if len(paths) > MAX_FILES:
            paths = paths[:MAX_FILES]
        results = {}
        for path in paths:
            results[path] = self.read_file(path, max_chars=max_chars_each)
        return {"files": results, "count": len(results), "note": f"Limitado a {MAX_FILES} arquivos por chamada"}

    def read_file_chunked(self, path: str, chunk_size: int = 6000, chunk_index: int = 0) -> dict:
        """
        Lê um arquivo grande em partes (chunks).
        Use quando um arquivo for muito grande para ler de uma vez.
        chunk_index=0 é o primeiro chunk, 1 o segundo, etc.
        Retorna também total_chunks para saber quantas partes existem.
        """
        p = self._check(path)
        if not p.exists():
            return {"error": f"Arquivo não existe: {p}"}
        if not p.is_file():
            return {"error": f"Não é um arquivo: {p}"}

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"error": f"Erro ao ler arquivo: {e}"}

        total_len = len(content)
        total_chunks = max(1, (total_len + chunk_size - 1) // chunk_size)

        if chunk_index >= total_chunks:
            return {
                "error": f"chunk_index {chunk_index} fora do range. Total de chunks: {total_chunks}"
            }

        start = chunk_index * chunk_size
        end = start + chunk_size
        chunk_content = content[start:end]

        return {
            "path": str(p),
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "chunk_size": chunk_size,
            "content": chunk_content,
            "has_more": chunk_index < total_chunks - 1,
            "total_chars": total_len,
        }

    def scan_project(self, path: str, max_files: int = 30) -> dict:
        """
        Faz uma varredura inteligente de um projeto:
        1. Lista a estrutura de diretórios (2 níveis)
        2. Lê automaticamente os arquivos mais importantes:
           package.json, Cargo.toml, pyproject.toml, requirements.txt,
           README.md, .env.example, src/main.*, index.*, app.*, main.*
        Retorna tudo para o modelo analisar de verdade.
        """
        p = self._check(path)
        if not p.is_dir():
            return {"error": f"Não é um diretório: {p}"}

        # 1. Estrutura em 2 níveis
        structure = []
        try:
            for item in sorted(p.iterdir()):
                if item.name.startswith(".") and item.name not in (".env.example", ".env"):
                    continue
                try:
                    _is_dir = item.is_dir()
                except OSError:
                    _is_dir = False
                entry = {"name": item.name, "type": "dir" if _is_dir else "file"}
                if _is_dir and item.name not in ("node_modules", ".git", "__pycache__", "dist", "build", ".next", "venv", ".venv"):
                    try:
                        _children = []
                        for c in sorted(item.iterdir()):
                            try:
                                _c_is_dir = c.is_dir()
                            except OSError:
                                _c_is_dir = False
                            if not c.name.startswith(".") or c.name in (".env.example",):
                                _children.append({"name": c.name, "type": "dir" if _c_is_dir else "file"})
                        entry["children"] = _children[:20]
                    except OSError:
                        entry["children"] = []
                structure.append(entry)
        except Exception as e:
            return {"error": f"Erro ao listar estrutura: {e}"}

        # 2. Arquivos prioritários para leitura automática
        priority_names = [
            # Build configs
            "package.json", "Cargo.toml", "pyproject.toml", "requirements.txt",
            "tsconfig.json", "Makefile", "docker-compose.yml", "Dockerfile",
            # Docs
            "README.md", "README", "CHANGELOG.md",
            # Env
            ".env.example", ".env.sample",
            # Solana / Anchor específicos
            "Anchor.toml", "anchor/Cargo.toml", "programs/*/Cargo.toml",
            # Python
            "setup.py", "setup.cfg", "poetry.lock",
            # Node
            "package-lock.json", "yarn.lock",
        ]
        priority_globs = [
            # Entry points
            "src/main.*", "src/index.*", "src/app.*", "src/lib.*",
            "app/main.*", "index.*", "main.*", "app.*", "server.*",
            # Solana programs
            "programs/*/src/lib.rs", "programs/*/src/state.rs",
            "programs/*/src/errors.rs", "programs/*/src/instructions/*.rs",
            # Smart contracts
            "contracts/*.sol", "src/**/*.sol",
            # Source code
            "src/**/*.ts", "src/**/*.py", "src/**/*.rs",
        ]

        to_read = []

        # Arquivos na raiz por nome
        for name in priority_names:
            candidate = p / name
            if candidate.exists() and candidate.is_file() and self.is_allowed(candidate):
                to_read.append(candidate)

        # Globs para src/
        for pattern in priority_globs:
            for match in sorted(p.glob(pattern)):
                if match.is_file() and self.is_allowed(match) and match not in to_read:
                    to_read.append(match)
                if len(to_read) >= max_files:
                    break
            if len(to_read) >= max_files:
                break

        # Ler os arquivos coletados
        file_contents = {}
        for f in to_read[:max_files]:
            result = self.read_file(str(f), max_chars=5000)
            if "error" not in result:
                rel = str(f.relative_to(p))
                file_contents[rel] = result["content"]

        return {
            "project_root": str(p),
            "structure": structure,
            "files_read": file_contents,
            "files_read_count": len(file_contents),
        }

    # ── Web Search ────────────────────────────────────────────────────────

    def web_search(self, query: str, max_results: int = 5) -> dict:
        """
        Busca na web usando DuckDuckGo (sem API key).
        Use para: documentação de bibliotecas, CVEs, vulnerabilidades Web3,
        exemplos de código, releases de versão, etc.
        """
        try:
            import urllib.request
            import urllib.parse
            import re

            # DuckDuckGo HTML search (sem JS, mais simples)
            encoded = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; Luna-Agent/2.1; research)",
                "Accept": "text/html",
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            # Extrair resultados simples com regex
            # Padrão de links nos resultados do DDG HTML
            results = []
            # Extrair snippets de texto dos resultados
            snippets = re.findall(
                r'class="result__snippet"[^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            )
            titles = re.findall(
                r'class="result__a"[^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            )
            urls_found = re.findall(
                r'class="result__url"[^>]*>(.*?)</span>',
                html,
                re.DOTALL,
            )

            # Limpar HTML tags
            def clean(s: str) -> str:
                s = re.sub(r"<[^>]+>", "", s)
                return s.strip()

            for i in range(min(max_results, len(snippets))):
                results.append({
                    "title": clean(titles[i]) if i < len(titles) else "",
                    "url": clean(urls_found[i]) if i < len(urls_found) else "",
                    "snippet": clean(snippets[i]),
                })

            if not results:
                return {
                    "query": query,
                    "results": [],
                    "note": "Nenhum resultado encontrado ou formato inesperado",
                }

            return {"query": query, "results": results, "count": len(results)}

        except Exception as e:
            # Fallback: tentar com curl via subprocess
            try:
                import urllib.parse
                encoded = urllib.parse.quote_plus(query)
                result = subprocess.run(
                    f'curl -s --max-time 10 -A "Mozilla/5.0" '
                    f'"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"',
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                )
                if result.returncode == 0 and result.stdout:
                    import json
                    data = json.loads(result.stdout)
                    results = []
                    # Abstract
                    if data.get("Abstract"):
                        results.append({
                            "title": data.get("Heading", query),
                            "url": data.get("AbstractURL", ""),
                            "snippet": data["Abstract"][:400],
                        })
                    # Related topics
                    for topic in data.get("RelatedTopics", [])[:max_results - 1]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append({
                                "title": topic.get("FirstURL", ""),
                                "url": topic.get("FirstURL", ""),
                                "snippet": topic["Text"][:300],
                            })
                    return {"query": query, "results": results, "count": len(results)}
            except Exception:
                pass

            return {"error": f"Erro ao buscar na web: {e}", "query": query}

    # ── Acesso Dinâmico ───────────────────────────────────────────────────

    def allow_dir(self, path: str) -> dict:
        """Adiciona um diretório à whitelist em tempo de execução."""
        try:
            p = Path(path).resolve()
            if not p.exists():
                return {"error": f"Diretório não existe: {p}"}
            if p not in self.allowed_dirs:
                self.allowed_dirs.append(p)
            return {"ok": True, "allowed": str(p), "total": len(self.allowed_dirs)}
        except Exception as e:
            return {"error": str(e)}

    # ── Execução ─────────────────────────────────────────────────────────

    # Timeouts inteligentes por tipo de comando (segundos)
    _CMD_TIMEOUTS = {
        "grep":   120,   # projetos grandes precisam de tempo
        "rg":     120,
        "find":    90,
        "npm":    180,
        "yarn":   180,
        "cargo":  300,
        "anchor": 300,
        "pip":    120,
        "git":     60,
        "pytest":  90,
        "jest":   120,
        "node":    60,
        "python":  60,
    }

    def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 0,   # 0 = auto-detect
    ) -> dict:
        """
        Executa um comando shell no diretório especificado.
        Timeout automático por tipo de comando (grep=120s, cargo=300s, etc.)
        O cwd deve estar dentro dos diretórios permitidos.
        """
        # Validar cwd
        if cwd:
            work_dir = self._check(cwd)
        elif self.allowed_dirs:
            work_dir = self.allowed_dirs[0]
        else:
            return {"error": "Nenhum diretório de trabalho configurado"}

        # Bloquear comandos destrutivos — strings exatas + regex para bypasses conhecidos
        _BLOCKED_SIMPLE = [
            "rmdir /s", "format", "mkfs", "dd if=",
            "shutdown", "reboot", "halt", "init 0", "init 6",
            "sudo rm", "sudo dd", "sudo mkfs", "sudo format",
            "invoke-expression", "iex ",        # PowerShell exec remoto
            "> /dev/",                           # redirect para device
        ]
        _BLOCKED_REGEX = [
            r"rm\s+-[a-z]*r",           # rm -r, rm -rf, rm -fr, rm -rfd …
            r"del\s+/[sqf]",            # del /q /s /f (Windows)
            r"del\s+\S*\*",             # del *.*, del C:\* (wildcard destrutivo)
            r"curl\b.*\|",              # curl ... | sh / bash
            r"wget\b.*\|",              # wget ... | sh / bash
            r"powershell\b.*remove-item",
            r"powershell\b.*\brm\b",
            r"git\s+clean\s+-[a-z]*f",  # git clean -f, -fd, -fdx …
            r">\s*/dev/",               # redirect para /dev/null ou similar
        ]
        cmd_lower = command.lower().strip()
        for b in _BLOCKED_SIMPLE:
            if b in cmd_lower:
                return {"error": f"Comando bloqueado por política de segurança: '{b}'"}
        for pat in _BLOCKED_REGEX:
            if _re.search(pat, cmd_lower):
                return {"error": f"Comando bloqueado por política de segurança (padrão perigoso detectado)"}

        # Auto-detectar timeout baseado no comando
        if timeout <= 0:
            first_word = cmd_lower.split()[0].split("/")[-1] if cmd_lower.split() else ""
            timeout = self._CMD_TIMEOUTS.get(first_word, 60)  # default 60s

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            stdout = result.stdout
            stderr = result.stderr

            # Para grep com muito output, resumir para não explodir o contexto
            lines = stdout.splitlines()
            if len(lines) > 200:
                stdout = "\n".join(lines[:200]) + f"\n... [{len(lines) - 200} linhas adicionais omitidas — use grep com --max-count=200 ou filtre melhor]"

            return {
                "command": command,
                "cwd": str(work_dir),
                "stdout": stdout[:6000],
                "stderr": stderr[:2000],
                "returncode": result.returncode,
                "ok": result.returncode == 0,
                "timeout_used": timeout,
            }
        except subprocess.TimeoutExpired:
            return {
                "error": f"Timeout após {timeout}s",
                "command": command,
                "suggestion": (
                    "O comando demorou demais. Tente:\n"
                    "1. Buscar em subdiretório menor: adicione 'src/' ou 'api/' ao path\n"
                    "2. Adicionar --max-count=50 para limitar resultados\n"
                    "3. Simplificar o padrão: buscar um termo por vez\n"
                    f"Ex: grep -rn 'auth' --include='*.ts' --max-count=50 src/"
                ),
            }
        except Exception as e:
            return {"error": f"Erro ao executar comando: {e}"}

    # ── Definições OpenAI Function Calling ───────────────────────────────

    @staticmethod
    def get_tool_definitions() -> list[dict]:
        """Retorna as definições das tools no formato OpenAI function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_dir",
                    "description": "Lista arquivos e pastas de um diretório no PC do usuário",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Caminho do diretório (ex: /mnt/d/Dev)"},
                            "show_hidden": {"type": "boolean", "description": "Mostrar arquivos ocultos", "default": False},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Lê o conteúdo de um arquivo no PC do usuário",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Caminho completo do arquivo"},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Cria ou sobrescreve um arquivo com o conteúdo fornecido",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Caminho completo do arquivo"},
                            "content": {"type": "string", "description": "Conteúdo a escrever"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "patch_file",
                    "description": "Substitui um trecho específico de texto em um arquivo existente",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Caminho do arquivo"},
                            "old": {"type": "string", "description": "Texto a ser substituído"},
                            "new": {"type": "string", "description": "Novo texto"},
                        },
                        "required": ["path", "old", "new"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Busca arquivos por padrão (glob) dentro de um diretório",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Diretório raiz da busca"},
                            "pattern": {"type": "string", "description": "Padrão glob (ex: '*.py', '**/*.ts')"},
                        },
                        "required": ["path", "pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "grep_file",
                    "description": "Busca texto dentro de um arquivo",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Caminho do arquivo"},
                            "query": {"type": "string", "description": "Texto a buscar"},
                        },
                        "required": ["path", "query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Executa um comando shell no PC do usuário. PROIBIDO usar para busca de arquivos: nunca use 'dir /s', 'find -name', 'ls -R' — use search_files ou list_dir para isso (mais rápido e não consome budget de run_command). Reserve run_command para: git, npm, python, testes, audit, compilação.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Comando a executar (ex: 'git status', 'npm install')"},
                            "cwd": {"type": "string", "description": "Diretório de trabalho (opcional)"},
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_dir",
                    "description": "Cria um diretório (e subdiretórios necessários)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Caminho do diretório a criar"},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scan_project",
                    "description": (
                        "PRIMEIRA FERRAMENTA A USAR quando o usuário pedir para analisar, revisar ou entender um projeto. "
                        "Lê automaticamente a estrutura + arquivos-chave do projeto (package.json, README, src/, etc.) "
                        "de uma vez. Use ANTES de qualquer outra análise."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Caminho raiz do projeto"},
                            "max_files": {"type": "integer", "description": "Número máximo de arquivos a ler (padrão 30)", "default": 30},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_many",
                    "description": "Lê múltiplos arquivos de uma vez. Use quando precisar ler vários arquivos relacionados.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Lista de caminhos completos dos arquivos a ler",
                            },
                        },
                        "required": ["paths"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "allow_dir",
                    "description": "Adiciona um diretório externo à lista de acesso. PROIBIDO usar para: workspace ativo, D:\\luna-agent, C:\\Dev, D:\\Dev, C:\\Users — todos já estão pré-autorizados. Use SOMENTE para caminhos completamente diferentes que o usuário mencionar explicitamente (ex: E:\\OutroProjeto). Nunca use para buscar arquivos — use search_files ou list_dir.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Caminho do diretório a liberar"},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file_chunked",
                    "description": (
                        "Lê um arquivo grande em partes (chunks). "
                        "Use quando read_file retornar conteúdo truncado ou quando precisar ler "
                        "partes específicas de arquivos grandes. "
                        "Chame com chunk_index=0 para a primeira parte, 1 para a segunda, etc. "
                        "O retorno inclui 'total_chunks' e 'has_more' para saber se há mais partes."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Caminho do arquivo"},
                            "chunk_size": {
                                "type": "integer",
                                "description": "Tamanho de cada parte em caracteres (padrão: 6000)",
                                "default": 6000,
                            },
                            "chunk_index": {
                                "type": "integer",
                                "description": "Índice da parte a ler (0 = primeira parte)",
                                "default": 0,
                            },
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": (
                        "Busca informações na web. Use para: documentação de bibliotecas e frameworks, "
                        "CVEs e vulnerabilidades conhecidas, bugs relatados em projetos, "
                        "exemplos de código, preços de tokens, releases mais recentes, "
                        "documentação Solana/Anchor/Ethereum, writeups de bug bounty. "
                        "NÃO invente informações — se não sabe algo, busque primeiro."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Consulta de busca em inglês ou português",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Número máximo de resultados (padrão: 5)",
                                "default": 5,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
        ]
