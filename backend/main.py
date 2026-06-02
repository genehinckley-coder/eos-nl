import logging
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routes.translate import router as translate_router
from routes.status import router as status_router
from config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="EOS NL Bridge", version="0.1.0")

app.include_router(translate_router)
app.include_router(status_router)

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
