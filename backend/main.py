import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routes.translate import router as translate_router
from routes.status import router as status_router
from routes.board_state import router as board_state_router
from eos_client import eos_client
from config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.eos_host:
        try:
            await eos_client.connect()
        except Exception as exc:
            logger.warning("EOS not reachable at startup: %s. Listener will retry.", exc)
    await eos_client.start_listening()
    yield
    await eos_client.close()


app = FastAPI(title="EOS NL Bridge", version="0.2.0", lifespan=lifespan)

app.include_router(translate_router)
app.include_router(status_router)
app.include_router(board_state_router)

# Serve the frontend from the sibling `frontend/` directory.
# This mount must come last so API routes take precedence.
app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
    )
