from fastapi import APIRouter
from pydantic import BaseModel
import ollama_client
import sanitizer
from sanitizer import TranslationError, DestructiveCommandError
from eos_client import eos_client, EosUnreachableError
from config import settings

router = APIRouter()


class TranslateRequest(BaseModel):
    input: str


class TranslateResponse(BaseModel):
    ok: bool
    syntax: str | None
    source: str
    sent: bool
    error: str | None


@router.post("/api/translate", response_model=TranslateResponse)
async def translate(body: TranslateRequest) -> TranslateResponse:
    raw_input = (body.input or "").strip()
    if not raw_input:
        return TranslateResponse(ok=False, syntax=None, source="bridge", sent=False, error="empty input")

    # --- Translation ---
    try:
        raw = await ollama_client.translate(raw_input)
    except ollama_client.OllamaError as exc:
        return TranslateResponse(ok=False, syntax=None, source=settings.model_name, sent=False, error=str(exc))

    # --- Sanitization ---
    try:
        syntax = sanitizer.clean(raw)
    except DestructiveCommandError as exc:
        return TranslateResponse(
            ok=False,
            syntax=exc.syntax,
            source=settings.model_name,
            sent=False,
            error=str(exc),
        )
    except TranslationError as exc:
        return TranslateResponse(ok=False, syntax=None, source=settings.model_name, sent=False, error=str(exc))

    # --- OSC Dispatch ---
    if not settings.eos_host:
        return TranslateResponse(
            ok=False,
            syntax=syntax,
            source=settings.model_name,
            sent=False,
            error="EOS_HOST not configured — set it in backend/.env",
        )

    try:
        await eos_client.send_cmd(syntax)
    except EosUnreachableError as exc:
        return TranslateResponse(
            ok=False,
            syntax=syntax,
            source=settings.model_name,
            sent=False,
            error=f"EOS unreachable: {exc}",
        )

    return TranslateResponse(ok=True, syntax=syntax, source=settings.model_name, sent=True, error=None)
