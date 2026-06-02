import asyncio
import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from config import settings

router = APIRouter()


class StatusResponse(BaseModel):
    ollama: str
    eos: str
    eos_host: str
    model: str


@router.get("/api/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    ollama_status = await _check_ollama()
    eos_status = await _check_eos()
    return StatusResponse(
        ollama=ollama_status,
        eos=eos_status,
        eos_host=settings.eos_host or "(not configured)",
        model=settings.model_name,
    )


async def _check_ollama() -> str:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{settings.ollama_url}/api/tags", timeout=3.0)
            return "ok" if r.status_code == 200 else f"error (HTTP {r.status_code})"
    except Exception as exc:
        return f"error ({exc})"


async def _check_eos() -> str:
    if not settings.eos_host:
        return "unconfigured"
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.eos_host, settings.eos_port),
            timeout=2.0,
        )
        writer.close()
        await writer.wait_closed()
        return "ok"
    except asyncio.TimeoutError:
        return "error (timeout)"
    except Exception as exc:
        return f"error ({exc})"
