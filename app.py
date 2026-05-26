from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from adapters import adapter_from_env
from config import get_default_provider, get_all_provider_names


ROOT = Path(__file__).resolve().parent

app = FastAPI(title="Live Frame Console")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/providers")
async def providers() -> JSONResponse:
    return JSONResponse({"providers": get_all_provider_names()})


@app.websocket("/ws/session")
async def session(websocket: WebSocket) -> None:
    await websocket.accept()
    provider = websocket.query_params.get("provider") or get_default_provider()
    adapter = adapter_from_env(provider)
    await adapter.run(websocket)
