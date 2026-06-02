import httpx
from config import settings


class OllamaError(Exception):
    pass


async def translate(text: str) -> str:
    """Send bare natural-language text to eos-nl:v4 and return the EOS syntax string.

    The model was fine-tuned to respond directly without a system prompt — the input
    is the user's natural language, the output is EOS command-line syntax.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.model_name,
                    "prompt": text,
                    "stream": False,
                },
                timeout=30.0,
            )
            response.raise_for_status()
    except httpx.TimeoutException:
        raise OllamaError(f"Ollama timed out after 30s (model: {settings.model_name})")
    except httpx.HTTPStatusError as exc:
        raise OllamaError(f"Ollama returned HTTP {exc.response.status_code}")
    except httpx.ConnectError:
        raise OllamaError(f"Cannot connect to Ollama at {settings.ollama_url}")

    data = response.json()
    result = data.get("response", "").strip()
    if not result:
        raise OllamaError("Ollama returned an empty response")
    return result
