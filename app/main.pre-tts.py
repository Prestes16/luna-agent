from pathlib import Path
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
STATIC_DIR = BASE_DIR / "app" / "static"

app = FastAPI(title="Luna Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def build_system_prompt() -> str:
    parts = [
        read_text_file(PROMPTS_DIR / "identity.md"),
        read_text_file(PROMPTS_DIR / "rules.md"),
        read_text_file(PROMPTS_DIR / "memory-viva.md"),
        read_text_file(PROMPTS_DIR / "voice-personality.md"),
        read_text_file(PROMPTS_DIR / "workstyle.md"),
        read_text_file(PROMPTS_DIR / "modes" / "dev.md"),
    ]
    return "\n\n".join(part for part in parts if part)


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key)


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    identity = read_text_file(PROMPTS_DIR / "identity.md")
    rules = read_text_file(PROMPTS_DIR / "rules.md")
    memory = read_text_file(PROMPTS_DIR / "memory-viva.md")

    return {
        "success": True,
        "response": {
            "status": "ok",
            "identity_loaded": bool(identity),
            "rules_loaded": bool(rules),
            "memory_loaded": bool(memory)
        }
    }


@app.post("/chat")
def chat(payload: ChatRequest):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    model = os.getenv("LUNA_MODEL", "gpt-5.4").strip() or "gpt-5.4"
    system_prompt = build_system_prompt()
    client = get_client()

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        )
        return {
            "success": True,
            "response": {
                "text": response.output_text
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")
