# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "python-dotenv>=1.0",
#   "requests>=2.32",
# ]
# ///
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

API_ROOT = "https://openrouter.ai/api/v1"
MAX_INPUT_BYTES = 20 * 1024 * 1024

ALIASES = {
    "flash": "google/gemini-3.1-flash-image",
    "pro": "google/gemini-3-pro-image",
    "gpt2": "openai/gpt-image-2",
    "gpt": "openai/gpt-image-2",
    "flux": "black-forest-labs/flux.2-pro",
    "flux-max": "black-forest-labs/flux.2-max",
    "seedream": "bytedance-seed/seedream-5-0-lite",
    "seedream-pro": "bytedance-seed/seedream-5-0-pro",
    "seedream-4.5": "bytedance-seed/seedream-4.5",
    "qwen": "qwen/qwen-image-3-pro",
    "grok": "x-ai/grok-imagine-image-2.0",
}


def load_project_env() -> None:
    env_file = Path.cwd() / ".env"
    if env_file.is_file():
        load_dotenv(dotenv_path=env_file, override=False)


def require_external(allowed: bool) -> None:
    if not allowed:
        raise SystemExit(
            "ERROR: external processing is disabled. "
            "Obtain explicit user authorization for this task, then pass --allow-external."
        )


def get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit(
            "ERROR: OPENROUTER_API_KEY is not set in the process environment "
            "or current working directory .env."
        )
    return key


def resolve_model(name: str) -> str:
    return ALIASES.get(name.lower(), name)


def headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Prestes16/luna-agent",
        "X-Title": "Luna Cyber openrouter-img",
    }


def input_data_url(raw_path: str) -> str:
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"ERROR: input image not found: {path}")

    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise SystemExit(
            f"ERROR: input image is {size} bytes; maximum is {MAX_INPUT_BYTES} bytes."
        )

    mime, _ = mimetypes.guess_type(path.name)
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        raise SystemExit(
            f"ERROR: unsupported input image type {mime!r}; use PNG, JPG/JPEG or WebP."
        )

    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def safe_http_error(response: requests.Response) -> str:
    body = response.text[:1000]
    return f"OpenRouter HTTP {response.status_code}: {body}"


def build_request(args: argparse.Namespace) -> tuple[str, dict]:
    model = resolve_model(args.model)
    body: dict = {
        "model": model,
        "prompt": args.prompt,
        "n": 1,
    }
    if args.resolution:
        body["resolution"] = args.resolution
    if args.aspect_ratio:
        body["aspect_ratio"] = args.aspect_ratio
    if args.quality:
        body["quality"] = args.quality
    if args.input_image:
        body["input_references"] = [
            {
                "type": "image_url",
                "image_url": {"url": input_data_url(args.input_image)},
            }
        ]
    return model, body


def list_models(key: str) -> None:
    response = requests.get(
        f"{API_ROOT}/images/models",
        headers=headers(key),
        timeout=60,
    )
    if response.status_code != 200:
        raise SystemExit(f"ERROR: {safe_http_error(response)}")

    data = response.json().get("data") or []
    for model in data:
        model_id = model.get("id")
        if model_id:
            print(model_id)


def generate(args: argparse.Namespace, key: str) -> None:
    model, body = build_request(args)

    if args.dry_run:
        preview = dict(body)
        if "input_references" in preview:
            preview["input_references"] = "[local image encoded only during real request]"
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return

    response = requests.post(
        f"{API_ROOT}/images",
        headers=headers(key),
        json=body,
        timeout=300,
    )
    if response.status_code != 200:
        raise SystemExit(f"ERROR: {safe_http_error(response)}")

    data = response.json()
    items = data.get("data") or []
    encoded = items[0].get("b64_json") if items else None
    if not encoded:
        raise SystemExit(
            "ERROR: OpenRouter returned no b64_json image payload."
        )

    out = Path(args.filename).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise SystemExit(f"ERROR: invalid base64 image payload: {exc}") from exc

    out.write_bytes(image_bytes)
    print(f"image_saved={out}")
    print(f"model={model}")

    usage = data.get("usage") or {}
    if usage.get("cost") is not None:
        print(f"usage_cost_usd={usage['cost']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gated OpenRouter image generation/editing for Luna/Codex."
    )
    parser.add_argument(
        "--allow-external",
        action="store_true",
        help="Mechanical opt-in for network/external processing; user authorization is also required.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--prompt")
    parser.add_argument("--filename")
    parser.add_argument("--input-image")
    parser.add_argument("--model", default="flash")
    parser.add_argument("--resolution", default="1K")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--quality")
    args = parser.parse_args()

    if not args.list_models and (not args.prompt or not args.filename):
        parser.error("--prompt and --filename are required unless --list-models is used")
    return args


def main() -> None:
    args = parse_args()

    # A dry-run is intentionally local and can execute without authorization or credentials.
    if args.dry_run:
        if args.list_models:
            raise SystemExit("ERROR: --dry-run cannot be combined with --list-models")
        model, body = build_request(args)
        preview = dict(body)
        if "input_references" in preview:
            preview["input_references"] = "[local image would be encoded for an authorized request]"
        print(json.dumps({"model": model, "request": preview}, indent=2, ensure_ascii=False))
        return

    require_external(args.allow_external)
    load_project_env()
    key = get_api_key()

    if args.list_models:
        list_models(key)
        return

    generate(args, key)


if __name__ == "__main__":
    main()
