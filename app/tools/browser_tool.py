"""
Luna Browser Tool - Playwright headless wrapper.

Capacidades:
- Navegar URL, screenshot, extrair HTML/text
- Capturar requests XHR/fetch (util em recon de SPA)
- Executar JavaScript no contexto da pagina
- Preencher forms e clicar (PoC XSS, validacao de flows)
- Dump de console logs e network

Requer: playwright. Instalar via: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Optional


def _ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa
        return True
    except ImportError:
        return False


def browser_navigate(url: str, screenshot: bool = True,
                     wait_until: str = "networkidle", timeout_s: int = 30,
                     user_agent: Optional[str] = None) -> dict:
    """
    Abre URL em Chromium headless, captura HTML + console + requests.
    Retorna dict com html_preview, screenshot_b64 (opcional), title, status, requests, console.
    """
    if not _ensure_playwright():
        return {"ok": False, "error": "playwright not installed",
                "install": "pip install playwright && playwright install chromium"}
    from playwright.sync_api import sync_playwright

    result = {"ok": False, "url": url, "requests": [], "console": []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx_kwargs = {}
            if user_agent:
                ctx_kwargs["user_agent"] = user_agent
            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()

            page.on("console", lambda m: result["console"].append({"type": m.type, "text": m.text[:500]}))
            page.on("request", lambda r: result["requests"].append({"method": r.method, "url": r.url[:500], "type": r.resource_type}))

            response = page.goto(url, wait_until=wait_until, timeout=timeout_s * 1000)
            result["status"] = response.status if response else None
            result["title"] = page.title()
            result["final_url"] = page.url
            html = page.content()
            result["html_preview"] = html[:4000]
            result["html_size"] = len(html)

            if screenshot:
                png = page.screenshot(full_page=False)
                result["screenshot_b64"] = base64.b64encode(png).decode()

            browser.close()
            result["ok"] = True
    except Exception as e:
        result["error"] = str(e)
    return result


def browser_extract(url: str, selectors: dict[str, str], timeout_s: int = 30) -> dict:
    """
    Extrai conteudo de elementos por CSS selector.
    selectors: {"title": "h1", "price": ".price", "links": "a@href"}
    Use formato "selector@attr" para extrair atributo (default: textContent).
    """
    if not _ensure_playwright():
        return {"ok": False, "error": "playwright not installed"}
    from playwright.sync_api import sync_playwright

    extracted = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
            for key, sel in selectors.items():
                attr = None
                if "@" in sel:
                    sel, attr = sel.rsplit("@", 1)
                elements = page.query_selector_all(sel)
                values = []
                for el in elements[:50]:
                    if attr:
                        v = el.get_attribute(attr)
                    else:
                        v = el.inner_text()
                    if v is not None:
                        values.append(v.strip()[:500])
                extracted[key] = values if len(values) > 1 else (values[0] if values else None)
            browser.close()
        return {"ok": True, "url": url, "extracted": extracted}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_eval(url: str, script: str, timeout_s: int = 30) -> dict:
    """
    Navega e executa JavaScript. Retorna valor serializavel.
    Util para: dump de variaveis globais, detectar frameworks, pegar localStorage.
    """
    if not _ensure_playwright():
        return {"ok": False, "error": "playwright not installed"}
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
            value = page.evaluate(script)
            browser.close()
        return {"ok": True, "url": url, "value": value}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_fill_and_submit(url: str, form_selector: str, fields: dict[str, str],
                            submit_selector: Optional[str] = None, timeout_s: int = 30) -> dict:
    """
    Preenche form e submete. Retorna URL final + html pos-submit.
    fields: {"input[name=q]": "payload<script>", "input[name=email]": "x@y.z"}
    """
    if not _ensure_playwright():
        return {"ok": False, "error": "playwright not installed"}
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
            for sel, val in fields.items():
                page.fill(sel, val)
            if submit_selector:
                page.click(submit_selector)
            else:
                page.evaluate(f'document.querySelector("{form_selector}").submit()')
            page.wait_for_load_state("networkidle", timeout=timeout_s * 1000)
            html = page.content()
            final_url = page.url
            browser.close()
        return {"ok": True, "final_url": final_url, "html_preview": html[:4000]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_save_screenshot(url: str, out_path: str, full_page: bool = True, timeout_s: int = 30) -> dict:
    """Salva screenshot em arquivo. Util para relatorios de bug bounty."""
    if not _ensure_playwright():
        return {"ok": False, "error": "playwright not installed"}
    from playwright.sync_api import sync_playwright

    try:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
            page.screenshot(path=out_path, full_page=full_page)
            browser.close()
        return {"ok": True, "path": out_path}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_tool_definitions() -> list[dict]:
    return [
        {"type": "function", "function": {"name": "browser_navigate",
            "description": "Abre URL em Chromium headless, retorna HTML, title, status, requests e console",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string"},
                "screenshot": {"type": "boolean"},
                "user_agent": {"type": "string"},
            }, "required": ["url"]}}},
        {"type": "function", "function": {"name": "browser_extract",
            "description": "Extrai elementos por CSS selectors. Formato 'sel@attr' para atributos",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string"},
                "selectors": {"type": "object"},
            }, "required": ["url", "selectors"]}}},
        {"type": "function", "function": {"name": "browser_eval",
            "description": "Executa JavaScript na pagina. Use para detectar frameworks, dump localStorage",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string"},
                "script": {"type": "string"},
            }, "required": ["url", "script"]}}},
        {"type": "function", "function": {"name": "browser_fill_submit",
            "description": "Preenche form e submete. Util para PoC XSS/CSRF ou validar login flow",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string"},
                "form_selector": {"type": "string"},
                "fields": {"type": "object"},
                "submit_selector": {"type": "string"},
            }, "required": ["url", "form_selector", "fields"]}}},
        {"type": "function", "function": {"name": "browser_screenshot",
            "description": "Salva screenshot em arquivo. Use para anexar a relatorios de bounty",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string"},
                "out_path": {"type": "string"},
                "full_page": {"type": "boolean"},
            }, "required": ["url", "out_path"]}}},
    ]