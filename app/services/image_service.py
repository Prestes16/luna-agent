"""
app/services/image_service.py
─────────────────────────────────────────────────────────
Módulo de geração e edição de imagens da Luna.

Providers suportados:
  - openai    : DALL-E 3 (geração), DALL-E 2 (edição/variação)
  - stability : Stable Diffusion XL via Stability AI API v1

Capacidades:
  1. generate_image / generate_image_stability
  2. edit_image / edit_image_stability
  3. create_variation / create_variation_stability
  4. Armazenamento local em data/images/ com metadados JSON
  5. Galeria: listar, carregar, deletar imagens
"""

import os
import json
import uuid
import base64
import logging
import httpx
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("luna.image_service")

# ─── Diretórios ──────────────────────────────────────────
DATA_DIR   = Path(__file__).parent.parent.parent / "data"
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

META_FILE = IMAGES_DIR / "gallery.json"


# ─── Utilitários de metadados ────────────────────────────
def _load_gallery() -> list[dict]:
    if not META_FILE.exists():
        return []
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_gallery(gallery: list[dict]) -> None:
    META_FILE.write_text(json.dumps(gallery, indent=2, ensure_ascii=False), encoding="utf-8")


def _add_to_gallery(entry: dict) -> None:
    gallery = _load_gallery()
    gallery.insert(0, entry)           # mais recente primeiro
    gallery = gallery[:200]            # máx 200 itens
    _save_gallery(gallery)


# ─── Salvar imagem no disco ──────────────────────────────
def _save_image_bytes(image_bytes: bytes, ext: str = "png") -> str:
    """Salva bytes de imagem em disco e retorna o image_id."""
    image_id = str(uuid.uuid4())
    path = IMAGES_DIR / f"{image_id}.{ext}"
    path.write_bytes(image_bytes)
    return image_id


def _get_image_path(image_id: str) -> Optional[Path]:
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = IMAGES_DIR / f"{image_id}.{ext}"
        if p.exists():
            return p
    return None


# ─── 1. Geração de imagem (DALL-E 3) ────────────────────
def generate_image(
    api_key:  str,
    prompt:   str,
    size:     str = "1024x1024",
    quality:  str = "standard",
    style:    str = "vivid",
    n:        int = 1,
    project_id: str = "global",
) -> dict:
    """
    Gera imagem com DALL-E 3 a partir de um prompt.

    Parâmetros:
        size:    "1024x1024" | "1792x1024" | "1024x1792"
        quality: "standard" | "hd"
        style:   "vivid" | "natural"
        n:       sempre 1 (limitação do DALL-E 3)

    Retorna dict com:
        image_id, url_local, prompt_revised, size, quality, style, ts
    """
    valid_sizes = {"1024x1024", "1792x1024", "1024x1792"}
    if size not in valid_sizes:
        size = "1024x1024"

    try:
        import httpx as _httpx
        resp = _httpx.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json={
                "model":           "dall-e-3",
                "prompt":          prompt,
                "n":               1,
                "size":            size,
                "quality":         quality,
                "style":           style,
                "response_format": "b64_json",
            },
            timeout=90.0,
        )

        if resp.status_code != 200:
            err = resp.json().get("error", {}).get("message", resp.text[:200])
            return {"success": False, "error": err}

        data       = resp.json()
        b64        = data["data"][0]["b64_json"]
        revised    = data["data"][0].get("revised_prompt", prompt)
        img_bytes  = base64.b64decode(b64)
        image_id   = _save_image_bytes(img_bytes, "png")

        entry = {
            "image_id":       image_id,
            "type":           "generate",
            "prompt":         prompt,
            "prompt_revised": revised,
            "size":           size,
            "quality":        quality,
            "style":          style,
            "project_id":     project_id,
            "ts":             datetime.now(timezone.utc).isoformat(),
        }
        _add_to_gallery(entry)

        logger.info(f"[IMAGE] generated {image_id} | size={size} quality={quality}")
        return {"success": True, **entry, "url": f"/image/file/{image_id}"}

    except Exception as e:
        logger.error(f"[IMAGE] generate error: {e}")
        return {"success": False, "error": str(e)[:300]}


# ─── 2. Edição de imagem (DALL-E 2) ─────────────────────
def edit_image(
    api_key:     str,
    image_bytes: bytes,
    prompt:      str,
    mask_bytes:  Optional[bytes] = None,
    size:        str = "1024x1024",
    project_id:  str = "global",
) -> dict:
    """
    Edita uma região de imagem com DALL-E 2.
    A imagem e a máscara devem ser PNG com alpha (RGBA).
    Se mask_bytes for None, a API edita toda a imagem.
    """
    valid_sizes = {"256x256", "512x512", "1024x1024"}
    if size not in valid_sizes:
        size = "1024x1024"

    try:
        import httpx as _httpx

        files: dict = {
            "image":  ("image.png", image_bytes,  "image/png"),
            "prompt": (None,        prompt),
            "n":      (None,        "1"),
            "size":   (None,        size),
            "response_format": (None, "b64_json"),
        }
        if mask_bytes:
            files["mask"] = ("mask.png", mask_bytes, "image/png")

        resp = _httpx.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            timeout=90.0,
        )

        if resp.status_code != 200:
            err = resp.json().get("error", {}).get("message", resp.text[:200])
            return {"success": False, "error": err}

        data      = resp.json()
        b64       = data["data"][0]["b64_json"]
        img_bytes = base64.b64decode(b64)
        image_id  = _save_image_bytes(img_bytes, "png")

        entry = {
            "image_id":   image_id,
            "type":       "edit",
            "prompt":     prompt,
            "size":       size,
            "project_id": project_id,
            "ts":         datetime.now(timezone.utc).isoformat(),
        }
        _add_to_gallery(entry)

        logger.info(f"[IMAGE] edited {image_id}")
        return {"success": True, **entry, "url": f"/image/file/{image_id}"}

    except Exception as e:
        logger.error(f"[IMAGE] edit error: {e}")
        return {"success": False, "error": str(e)[:300]}


# ─── 3. Variações de imagem (DALL-E 2) ──────────────────
def create_variation(
    api_key:     str,
    image_bytes: bytes,
    size:        str = "1024x1024",
    n:           int = 2,
    project_id:  str = "global",
) -> dict:
    """
    Gera N variações de uma imagem com DALL-E 2.
    Imagem deve ser PNG quadrada (até 4MB).
    Retorna lista de image_ids.
    """
    valid_sizes = {"256x256", "512x512", "1024x1024"}
    if size not in valid_sizes:
        size = "1024x1024"
    n = max(1, min(n, 4))

    try:
        import httpx as _httpx

        resp = _httpx.post(
            "https://api.openai.com/v1/images/variations",
            headers={"Authorization": f"Bearer {api_key}"},
            files={
                "image":           ("image.png", image_bytes, "image/png"),
                "n":               (None, str(n)),
                "size":            (None, size),
                "response_format": (None, "b64_json"),
            },
            timeout=90.0,
        )

        if resp.status_code != 200:
            err = resp.json().get("error", {}).get("message", resp.text[:200])
            return {"success": False, "error": err}

        data    = resp.json()
        results = []
        for item in data["data"]:
            b64       = item["b64_json"]
            img_bytes = base64.b64decode(b64)
            image_id  = _save_image_bytes(img_bytes, "png")
            entry = {
                "image_id":   image_id,
                "type":       "variation",
                "size":       size,
                "project_id": project_id,
                "ts":         datetime.now(timezone.utc).isoformat(),
            }
            _add_to_gallery(entry)
            results.append({"image_id": image_id, "url": f"/image/file/{image_id}"})

        logger.info(f"[IMAGE] variations created: {len(results)}")
        return {"success": True, "images": results, "count": len(results)}

    except Exception as e:
        logger.error(f"[IMAGE] variation error: {e}")
        return {"success": False, "error": str(e)[:300]}


# ─── Stability AI ────────────────────────────────────────
STABILITY_V1_BASE = "https://api.stability.ai/v1/generation"
STABILITY_V2_BASE = "https://api.stability.ai/v2beta/stable-image"
STABILITY_SDXL    = "stable-diffusion-xl-1024-v1-0"

# Tamanhos válidos para SDXL 1024
STABILITY_VALID_SIZES = {
    "1024x1024", "1152x896", "1216x832", "1344x768",
    "1536x640",  "640x1536", "768x1344", "832x1216", "896x1152",
}

STABILITY_STYLE_PRESETS = [
    "none", "3d-model", "analog-film", "anime", "cinematic", "comic-book",
    "digital-art", "enhance", "fantasy-art", "isometric", "line-art",
    "low-poly", "neon-punk", "origami", "photographic", "pixel-art",
    "tile-texture", "modeling-compound",
]


def generate_image_stability(
    api_key:         str,
    prompt:          str,
    negative_prompt: str   = "",
    size:            str   = "1024x1024",
    steps:           int   = 30,
    cfg_scale:       float = 7.0,
    style_preset:    str   = "none",
    seed:            int   = 0,
    project_id:      str   = "global",
) -> dict:
    """Gera imagem via Stability AI SDXL (v1 API)."""
    if size not in STABILITY_VALID_SIZES:
        size = "1024x1024"
    steps    = max(10, min(steps, 150))
    cfg_scale = max(1.0, min(cfg_scale, 35.0))

    width, height = map(int, size.split("x"))

    text_prompts = [{"text": prompt, "weight": 1.0}]
    if negative_prompt.strip():
        text_prompts.append({"text": negative_prompt.strip(), "weight": -1.0})

    body: dict = {
        "text_prompts": text_prompts,
        "cfg_scale":    cfg_scale,
        "width":        width,
        "height":       height,
        "samples":      1,
        "steps":        steps,
    }
    if style_preset and style_preset != "none":
        body["style_preset"] = style_preset
    if seed:
        body["seed"] = seed

    try:
        resp = httpx.post(
            f"{STABILITY_V1_BASE}/{STABILITY_SDXL}/text-to-image",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
                "Accept":        "application/json",
            },
            json=body,
            timeout=120.0,
        )

        if resp.status_code != 200:
            try:
                msg = resp.json().get("message") or resp.text[:300]
            except Exception:
                msg = resp.text[:300]
            return {"success": False, "error": f"Stability API {resp.status_code}: {msg}"}

        data      = resp.json()
        artifacts = data.get("artifacts", [])
        if not artifacts:
            return {"success": False, "error": "Nenhuma imagem retornada pela Stability API"}

        artifact = artifacts[0]
        finish   = artifact.get("finishReason", "")
        if finish == "ERROR":
            return {"success": False, "error": "Stability API retornou ERROR"}

        img_bytes = base64.b64decode(artifact["base64"])
        image_id  = _save_image_bytes(img_bytes, "png")

        entry = {
            "image_id":      image_id,
            "type":          "stability-generate",
            "provider":      "stability",
            "prompt":        prompt,
            "negative_prompt": negative_prompt,
            "size":          size,
            "steps":         steps,
            "cfg_scale":     cfg_scale,
            "style_preset":  style_preset,
            "seed":          artifact.get("seed", 0),
            "finish_reason": finish,
            "project_id":    project_id,
            "ts":            datetime.now(timezone.utc).isoformat(),
        }
        _add_to_gallery(entry)
        logger.info(f"[STABILITY] generated {image_id} size={size} steps={steps}")
        return {"success": True, **entry, "url": f"/image/file/{image_id}"}

    except Exception as e:
        logger.error(f"[STABILITY] generate error: {e}")
        return {"success": False, "error": str(e)[:300]}


def edit_image_stability(
    api_key:         str,
    image_bytes:     bytes,
    prompt:          str,
    negative_prompt: str           = "",
    mask_bytes:      Optional[bytes] = None,
    project_id:      str           = "global",
) -> dict:
    """Edita imagem via Stability AI inpainting (v2beta API)."""
    files: list = [
        ("image",         ("image.png", image_bytes, "image/png")),
        ("prompt",        (None, prompt)),
        ("output_format", (None, "png")),
        ("grow_mask",     (None, "5")),
    ]
    if negative_prompt.strip():
        files.append(("negative_prompt", (None, negative_prompt.strip())))
    if mask_bytes:
        files.append(("mask", ("mask.png", mask_bytes, "image/png")))

    try:
        resp = httpx.post(
            f"{STABILITY_V2_BASE}/edit/inpaint",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept":        "application/json",
            },
            files=files,
            timeout=120.0,
        )

        if resp.status_code != 200:
            try:
                msg = resp.json().get("errors") or resp.json().get("name") or resp.text[:300]
            except Exception:
                msg = resp.text[:300]
            return {"success": False, "error": f"Stability API {resp.status_code}: {msg}"}

        data = resp.json()
        if "image" not in data:
            return {"success": False, "error": "Resposta sem campo 'image'"}

        img_bytes_out = base64.b64decode(data["image"])
        image_id      = _save_image_bytes(img_bytes_out, "png")

        entry = {
            "image_id":   image_id,
            "type":       "stability-edit",
            "provider":   "stability",
            "prompt":     prompt,
            "project_id": project_id,
            "ts":         datetime.now(timezone.utc).isoformat(),
        }
        _add_to_gallery(entry)
        logger.info(f"[STABILITY] edited {image_id}")
        return {"success": True, **entry, "url": f"/image/file/{image_id}"}

    except Exception as e:
        logger.error(f"[STABILITY] edit error: {e}")
        return {"success": False, "error": str(e)[:300]}


def create_variation_stability(
    api_key:         str,
    image_bytes:     bytes,
    prompt:          str   = "high quality variation",
    image_strength:  float = 0.35,
    size:            str   = "1024x1024",
    n:               int   = 2,
    cfg_scale:       float = 7.0,
    steps:           int   = 30,
    project_id:      str   = "global",
) -> dict:
    """Cria variações via Stability AI image-to-image (v1 API)."""
    if size not in STABILITY_VALID_SIZES:
        size = "1024x1024"
    n = max(1, min(n, 4))

    width, height    = map(int, size.split("x"))
    image_strength   = max(0.1, min(image_strength, 0.9))

    try:
        resp = httpx.post(
            f"{STABILITY_V1_BASE}/{STABILITY_SDXL}/image-to-image",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept":        "application/json",
            },
            files=[
                ("init_image",       ("image.png", image_bytes, "image/png")),
                ("init_image_mode",  (None, "IMAGE_STRENGTH")),
                ("image_strength",   (None, str(image_strength))),
                ("text_prompts[0][text]",   (None, prompt)),
                ("text_prompts[0][weight]", (None, "1")),
                ("cfg_scale", (None, str(cfg_scale))),
                ("steps",     (None, str(steps))),
                ("samples",   (None, str(n))),
                ("width",     (None, str(width))),
                ("height",    (None, str(height))),
            ],
            timeout=120.0,
        )

        if resp.status_code != 200:
            try:
                msg = resp.json().get("message") or resp.text[:300]
            except Exception:
                msg = resp.text[:300]
            return {"success": False, "error": f"Stability API {resp.status_code}: {msg}"}

        data      = resp.json()
        artifacts = data.get("artifacts", [])
        if not artifacts:
            return {"success": False, "error": "Nenhuma variação retornada"}

        results = []
        for artifact in artifacts:
            if artifact.get("finishReason") == "ERROR":
                continue
            img_bytes_out = base64.b64decode(artifact["base64"])
            image_id      = _save_image_bytes(img_bytes_out, "png")
            entry = {
                "image_id":   image_id,
                "type":       "stability-variation",
                "provider":   "stability",
                "prompt":     prompt,
                "size":       size,
                "project_id": project_id,
                "ts":         datetime.now(timezone.utc).isoformat(),
            }
            _add_to_gallery(entry)
            results.append({"image_id": image_id, "url": f"/image/file/{image_id}"})

        if not results:
            return {"success": False, "error": "Todas as variações falharam"}

        logger.info(f"[STABILITY] variations created: {len(results)}")
        return {"success": True, "images": results, "count": len(results)}

    except Exception as e:
        logger.error(f"[STABILITY] variation error: {e}")
        return {"success": False, "error": str(e)[:300]}


# ─── 4. Galeria ──────────────────────────────────────────
def get_gallery(limit: int = 50, project_id: Optional[str] = None) -> list[dict]:
    gallery = _load_gallery()
    if project_id:
        gallery = [e for e in gallery if e.get("project_id") == project_id]
    for entry in gallery:
        entry["url"] = f"/image/file/{entry['image_id']}"
    return gallery[:limit]


def delete_image(image_id: str) -> bool:
    path = _get_image_path(image_id)
    if path:
        path.unlink(missing_ok=True)

    gallery = [e for e in _load_gallery() if e.get("image_id") != image_id]
    _save_gallery(gallery)
    return path is not None


def get_image_bytes(image_id: str) -> Optional[bytes]:
    path = _get_image_path(image_id)
    if path:
        return path.read_bytes()
    return None
