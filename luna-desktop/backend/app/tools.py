"""
Luna Tools — File system + web access tools for the autonomous agent.

All file operations are sandboxed to the workspace_path provided by the user.
Web tools use httpx for async HTTP requests.
"""

import os
import re
import json
import logging
import mimetypes
import ipaddress
import urllib.parse as _urlparse
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Safety limits ─────────────────────────────────────────────────────────────
MAX_FILE_SIZE  = 512 * 1024   # 512 KB read limit
MAX_FETCH_SIZE = 256 * 1024   # 256 KB fetch limit
MAX_DIR_DEPTH  = 4            # max recursive depth for listing

# ── SSRF protection for fetch_url ─────────────────────────────────────────────
_SSRF_BLOCKED = [
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),   # AWS instance metadata
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
]

def _url_is_ssrf_safe(url: str) -> bool:
    """Block requests to private/internal IP ranges and known metadata endpoints."""
    try:
        parsed = _urlparse.urlparse(url)
        host = (parsed.hostname or '').lower()
        # Block common internal host names without DNS lookup
        if host in {'localhost', 'metadata', 'metadata.google.internal'}:
            return False
        if host.endswith('.local') or host.endswith('.internal'):
            return False
        # Block raw IP references to private ranges
        try:
            addr = ipaddress.ip_address(host)
            if any(addr in net for net in _SSRF_BLOCKED):
                return False
        except ValueError:
            pass  # hostname — can't resolve here, allow through
        return True
    except Exception:
        return False

# Text MIME types we're willing to read
TEXT_MIMES = {
    'text/', 'application/json', 'application/javascript',
    'application/typescript', 'application/xml', 'application/yaml',
    'application/x-yaml', 'application/toml',
}

def _is_text_file(path: str) -> bool:
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        return True  # unknown → try to read as text
    return any(mime.startswith(t) or mime == t for t in TEXT_MIMES)


def _safe_path(workspace: str, rel_path: str) -> Optional[str]:
    """
    Resolve rel_path inside workspace, reject path-traversal attempts.
    Uses os.path.normcase for comparison so Windows case differences (C:\\ vs c:\\)
    cannot bypass the check.
    """
    if not workspace:
        return None
    base = Path(workspace).resolve()
    full = (base / rel_path.lstrip('/\\')).resolve()
    # normcase lowercases on Windows, is a no-op on POSIX
    base_nc = os.path.normcase(str(base))
    full_nc = os.path.normcase(str(full))
    # Must be the base dir itself or start with base + separator
    if full_nc != base_nc and not full_nc.startswith(base_nc + os.sep):
        return None  # traversal attempt
    return str(full)


# ── File tools ─────────────────────────────────────────────────────────────────

def tool_list_directory(workspace: str, rel_path: str = '.', depth: int = 1) -> Dict[str, Any]:
    """List files/folders inside workspace. depth controls recursion."""
    base = _safe_path(workspace, rel_path)
    if not base:
        return {'error': 'Workspace não configurado ou caminho inválido'}
    if not os.path.isdir(base):
        return {'error': f'Não é um diretório: {rel_path}'}

    def _list(dir_path: str, current_depth: int) -> list:
        entries = []
        try:
            for name in sorted(os.listdir(dir_path)):
                if name.startswith('.') or name in {'node_modules', '__pycache__', '.git', 'dist', 'build'}:
                    continue
                full = os.path.join(dir_path, name)
                is_dir = os.path.isdir(full)
                rel = os.path.relpath(full, workspace)
                entry: Dict[str, Any] = {'name': name, 'path': rel, 'type': 'dir' if is_dir else 'file'}
                if not is_dir:
                    entry['size'] = os.path.getsize(full)
                if is_dir and current_depth < min(depth, MAX_DIR_DEPTH):
                    entry['children'] = _list(full, current_depth + 1)
                entries.append(entry)
        except PermissionError:
            pass
        return entries

    return {'path': rel_path, 'entries': _list(base, 1)}


def tool_read_file(workspace: str, rel_path: str) -> Dict[str, Any]:
    """Read a text file from the workspace."""
    full = _safe_path(workspace, rel_path)
    if not full:
        return {'error': 'Workspace não configurado ou caminho inválido'}
    if not os.path.isfile(full):
        return {'error': f'Arquivo não encontrado: {rel_path}'}
    if not _is_text_file(full):
        return {'error': f'Arquivo binário não suportado: {rel_path}'}

    size = os.path.getsize(full)
    if size > MAX_FILE_SIZE:
        return {'error': f'Arquivo muito grande ({size // 1024} KB). Limite: {MAX_FILE_SIZE // 1024} KB'}

    try:
        with open(full, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return {'path': rel_path, 'content': content, 'size': size}
    except Exception as e:
        return {'error': str(e)}


def tool_write_file(workspace: str, rel_path: str, content: str) -> Dict[str, Any]:
    """Write content to a file inside the workspace (creates dirs if needed)."""
    full = _safe_path(workspace, rel_path)
    if not full:
        return {'error': 'Workspace não configurado ou caminho inválido'}
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(content)
        return {'success': True, 'path': rel_path, 'bytes_written': len(content.encode())}
    except Exception as e:
        return {'error': str(e)}


def tool_create_directory(workspace: str, rel_path: str) -> Dict[str, Any]:
    """Create a directory (and parents) inside the workspace."""
    full = _safe_path(workspace, rel_path)
    if not full:
        return {'error': 'Workspace não configurado ou caminho inválido'}
    try:
        os.makedirs(full, exist_ok=True)
        return {'success': True, 'path': rel_path}
    except Exception as e:
        return {'error': str(e)}


def tool_delete_file(workspace: str, rel_path: str) -> Dict[str, Any]:
    """Delete a file (NOT a directory) from the workspace."""
    full = _safe_path(workspace, rel_path)
    if not full:
        return {'error': 'Workspace não configurado ou caminho inválido'}
    if not os.path.isfile(full):
        return {'error': f'Arquivo não encontrado: {rel_path}'}
    try:
        os.remove(full)
        return {'success': True, 'path': rel_path}
    except Exception as e:
        return {'error': str(e)}


# ── Web tools ─────────────────────────────────────────────────────────────────

async def tool_web_search(query: str, max_results: int = 6) -> Dict[str, Any]:
    """Search the web using DuckDuckGo and return structured results."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            # DuckDuckGo HTML endpoint (no JS required)
            resp = await client.post(
                'https://html.duckduckgo.com/html/',
                data={'q': query, 'kl': 'br-pt'},
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
                },
            )
            resp.raise_for_status()
            html = resp.text

        # Simple regex parsing — no BeautifulSoup dependency
        results = []
        # Match result blocks: title, url, snippet
        title_pat   = re.compile(r'<a[^>]+class="result__a"[^>]*>(.+?)</a>', re.S)
        url_pat     = re.compile(r'<a[^>]+class="result__url"[^>]*>\s*(.+?)\s*</a>', re.S)
        snippet_pat = re.compile(r'<a[^>]+class="result__snippet"[^>]*>(.+?)</a>', re.S)

        titles   = [re.sub(r'<[^>]+>', '', t).strip() for t in title_pat.findall(html)]
        urls     = [re.sub(r'<[^>]+>', '', u).strip() for u in url_pat.findall(html)]
        snippets = [re.sub(r'<[^>]+>', '', s).strip() for s in snippet_pat.findall(html)]

        for i in range(min(max_results, len(titles))):
            results.append({
                'title':   titles[i]   if i < len(titles)   else '',
                'url':     urls[i]     if i < len(urls)     else '',
                'snippet': snippets[i] if i < len(snippets) else '',
            })

        if not results:
            return {'query': query, 'results': [], 'note': 'Nenhum resultado encontrado'}

        return {'query': query, 'results': results}

    except Exception as e:
        logger.error(f'web_search error: {e}')
        return {'error': str(e), 'query': query}


async def tool_fetch_url(url: str, extract_text: bool = True) -> Dict[str, Any]:
    """Fetch a URL and return its content (text extraction or raw)."""
    if not url.startswith(('http://', 'https://')):
        return {'error': 'URL deve começar com http:// ou https://'}
    # SECURITY: block SSRF to private/internal networks
    if not _url_is_ssrf_safe(url):
        return {'error': 'URL bloqueada por política de segurança (IP privado/interno não permitido)'}
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; LunaAgent/3.0)'},
            )
            resp.raise_for_status()

        content_type = resp.headers.get('content-type', '')
        if 'html' in content_type and extract_text:
            # Strip HTML tags for cleaner LLM consumption
            text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.S)
            text = re.sub(r'<style[^>]*>.*?</style>',  '', text, flags=re.S)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s{3,}', '\n\n', text).strip()
            if len(text) > MAX_FETCH_SIZE:
                text = text[:MAX_FETCH_SIZE] + '\n\n[... truncado]'
            return {'url': url, 'content': text, 'content_type': 'text/plain'}
        else:
            raw = resp.text[:MAX_FETCH_SIZE]
            return {'url': url, 'content': raw, 'content_type': content_type}

    except Exception as e:
        logger.error(f'fetch_url error [{url}]: {e}')
        return {'error': str(e), 'url': url}


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lista arquivos e pastas no workspace do usuário. Use depth=3 na primeira chamada para ver a estrutura completa do projeto de uma vez.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":  {"type": "string", "description": "Caminho relativo dentro do workspace (padrão: '.')"},
                    "depth": {"type": "integer", "description": "Profundidade de listagem recursiva (1-4, padrão: 2 — use 3 para ver projeto completo)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lê o conteúdo de um arquivo texto no workspace do usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho relativo do arquivo dentro do workspace"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Cria ou substitui um arquivo no workspace do usuário com o conteúdo fornecido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "Caminho relativo do arquivo (cria diretórios automaticamente)"},
                    "content": {"type": "string", "description": "Conteúdo completo do arquivo"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Cria uma pasta (e subpastas) no workspace do usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho relativo da pasta a criar"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Pesquisa na internet via DuckDuckGo. Use para buscar documentação, CVEs, exploits, APIs, notícias e qualquer informação atual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":       {"type": "string", "description": "Termos de busca"},
                    "max_results": {"type": "integer", "description": "Número de resultados (padrão: 6, máx: 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Abre e lê o conteúdo de uma URL. Use para ler documentação, código fonte, relatórios de bugs, artigos técnicos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":          {"type": "string", "description": "URL completa (https://)"},
                    "extract_text": {"type": "boolean", "description": "Extrair texto limpo de HTML (padrão: true)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_workspace",
            "description": "Solicita ao usuário que selecione uma pasta do PC para dar acesso ao workspace. Use SEMPRE que o usuário pedir para trabalhar com arquivos locais e nenhum workspace estiver configurado. Isso abre o seletor de pasta nativo no desktop do usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Explique brevemente por que precisa de acesso à pasta (ex: 'para ler e modificar o projeto Solana')"},
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_project_context",
            "description": "Salva um documento markdown estruturado com o estado atual do projeto — pendências, bugs, decisões, arquitetura. Este documento fica visível no painel lateral direito e persiste entre sessões. Use após análises profundas de código ou ao final de uma tarefa complexa para registrar o estado do projeto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":   {"type": "string", "description": "Título do documento (ex: 'Luna Desktop - Estado Atual e Próximos Passos')"},
                    "content": {"type": "string", "description": "Conteúdo markdown completo do documento de contexto do projeto"},
                },
                "required": ["title", "content"],
            },
        },
    },
]

# Anthropic-format tools (slightly different schema)
TOOL_DEFINITIONS_CLAUDE = [
    {
        "name": "list_directory",
        "description": "Lista arquivos e pastas no workspace do usuário.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Caminho relativo (padrão: '.')"},
                "depth": {"type": "integer", "description": "Profundidade de listagem (1-4)"},
            },
        },
    },
    {
        "name": "read_file",
        "description": "Lê o conteúdo de um arquivo texto no workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho relativo do arquivo"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Cria ou substitui um arquivo no workspace com o conteúdo fornecido.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Caminho relativo do arquivo"},
                "content": {"type": "string", "description": "Conteúdo completo do arquivo"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "create_directory",
        "description": "Cria uma pasta (e subpastas) no workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho relativo da pasta"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "web_search",
        "description": "Pesquisa na internet via DuckDuckGo. Use para documentação, CVEs, exploits, APIs e informações atuais.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string", "description": "Termos de busca"},
                "max_results": {"type": "integer", "description": "Número de resultados (padrão: 6)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Abre e lê o conteúdo de uma URL — documentação, código, artigos técnicos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":          {"type": "string", "description": "URL completa"},
                "extract_text": {"type": "boolean", "description": "Extrair texto limpo de HTML"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "request_workspace",
        "description": "Solicita ao usuário que selecione uma pasta do PC. Use quando precisar de acesso ao sistema de arquivos e nenhum workspace estiver configurado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Motivo do pedido de acesso"},
            },
            "required": ["reason"],
        },
    },
    {
        "name": "save_project_context",
        "description": "Salva um documento markdown com o estado atual do projeto — pendências, bugs, decisões, arquitetura. Fica visível no painel lateral e persiste entre sessões.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":   {"type": "string", "description": "Título do documento"},
                "content": {"type": "string", "description": "Conteúdo markdown completo"},
            },
            "required": ["title", "content"],
        },
    },
]


async def execute_tool(name: str, args: Dict[str, Any], workspace: str) -> str:
    """Dispatch a tool call by name and return its JSON result string."""
    try:
        if name == 'list_directory':
            result = tool_list_directory(workspace, args.get('path', '.'), args.get('depth', 2))
        elif name == 'read_file':
            result = tool_read_file(workspace, args['path'])
        elif name == 'write_file':
            result = tool_write_file(workspace, args['path'], args['content'])
        elif name == 'create_directory':
            result = tool_create_directory(workspace, args['path'])
        elif name == 'delete_file':
            result = tool_delete_file(workspace, args['path'])
        elif name == 'web_search':
            result = await tool_web_search(args['query'], args.get('max_results', 6))
        elif name == 'fetch_url':
            result = await tool_fetch_url(args['url'], args.get('extract_text', True))
        elif name == 'request_workspace':
            # Special signal — frontend intercepts this event type in the SSE stream
            result = {'__action__': 'open_workspace_dialog', 'reason': args.get('reason', '')}
        elif name == 'save_project_context':
            title   = args.get('title', 'Contexto do Projeto')
            content = args.get('content', '')
            # Write to .luna/context.md inside workspace (if available)
            saved_path = None
            if workspace:
                luna_dir = os.path.join(workspace, '.luna')
                os.makedirs(luna_dir, exist_ok=True)
                ctx_path = os.path.join(luna_dir, 'context.md')
                with open(ctx_path, 'w', encoding='utf-8') as f:
                    f.write(f'# {title}\n\n{content}')
                saved_path = ctx_path
            # Signal frontend to update context panel
            result = {
                '__action__': 'project_context_updated',
                'title':   title,
                'content': f'# {title}\n\n{content}',
                'saved_path': saved_path,
            }
        else:
            result = {'error': f'Ferramenta desconhecida: {name}'}
    except KeyError as e:
        result = {'error': f'Parâmetro obrigatório ausente: {e}'}
    except Exception as e:
        result = {'error': str(e)}

    return json.dumps(result, ensure_ascii=False)
