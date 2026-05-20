from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from adapters import adapter_from_env


ROOT = Path(__file__).resolve().parent

app = FastAPI(title="Realtime Frame App")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.websocket("/ws/session")
async def session(websocket: WebSocket) -> None:
    await websocket.accept()
    provider = websocket.query_params.get("provider") or os.getenv("FRAME_APP_PROVIDER", "local-qwen")
    adapter = adapter_from_env(provider)
    await adapter.run(websocket)
