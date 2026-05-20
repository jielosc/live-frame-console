from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


def now_ms() -> int:
    return int(time.time() * 1000)


async def send_app_event(websocket: WebSocket, event_type: str, payload: dict[str, Any]) -> None:
    await websocket.send_text(json.dumps({"type": event_type, "timestamp": now_ms(), "payload": payload}, ensure_ascii=False))


class RealtimeAdapter:
    async def run(self, websocket: WebSocket) -> None:
        raise NotImplementedError


class LocalQwenAdapter(RealtimeAdapter):
    def __init__(self, url: str) -> None:
        self.url = url

    async def run(self, websocket: WebSocket) -> None:
        try:
            import websockets
        except ImportError:
            await send_app_event(websocket, "error", {"message": "Missing dependency: pip install websockets"})
            return

        try:
            async with websockets.connect(self.url) as upstream:
                to_upstream = asyncio.create_task(self._client_to_qwen(websocket, upstream))
                to_client = asyncio.create_task(self._qwen_to_client(upstream, websocket))
                done, pending = await asyncio.wait({to_upstream, to_client}, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                for task in done:
                    await task
        except WebSocketDisconnect:
            return
        except Exception as exc:
            await send_app_event(websocket, "error", {"message": f"Provider connection failed: {exc}"})

    async def _client_to_qwen(self, websocket: WebSocket, upstream: Any) -> None:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            mapped = self._to_qwen_event(event)
            if mapped:
                await upstream.send(json.dumps(mapped, ensure_ascii=False))
            if event.get("type") == "session.stop":
                return

    async def _qwen_to_client(self, upstream: Any, websocket: WebSocket) -> None:
        async for raw in upstream:
            event = json.loads(raw)
            mapped = self._from_qwen_event(event)
            if mapped:
                await send_app_event(websocket, mapped["type"], mapped["payload"])

    def _to_qwen_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = event.get("type")
        payload = event.get("payload") or {}

        if event_type == "session.start":
            max_frames = int(payload.get("maxFramesPerPrompt") or 24)
            return {
                "type": "session.start",
                "payload": {
                    "video_max_frames": max_frames,
                    "buffer_size": max(max_frames * 2, max_frames),
                    "capture_policy": payload.get("strategy") or "motion_mode",
                    "adaptive_policy": "fixed-frame-app-v1",
                },
            }

        if event_type == "media.frame":
            return {
                "type": "media.video_frame",
                "payload": {
                    "image_base64": payload.get("imageBase64"),
                    "width": payload.get("width"),
                    "height": payload.get("height"),
                    "client_capture_started_at_ms": payload.get("captureStartedAtMs"),
                    "client_capture_encoded_at_ms": payload.get("captureEncodedAtMs"),
                    "client_send_ts_ms": payload.get("clientSendAtMs"),
                    "client_capture_ms": payload.get("captureMs"),
                    "mode": payload.get("strategy"),
                    "frame_role": "regular",
                    "frame_input_mode": "images",
                    "sampling_policy": "fixed",
                    "target_width": payload.get("width"),
                    "target_height": payload.get("height"),
                },
            }

        if event_type == "prompt.ask":
            return {
                "type": "user.prompt",
                "payload": {
                    "prompt_id": payload.get("promptId") or uuid.uuid4().hex,
                    "text": payload.get("text") or "",
                    "max_new_tokens": int(payload.get("maxNewTokens") or 256),
                    "client_sent_at_ms": payload.get("clientSentAtMs") or now_ms(),
                },
            }

        if event_type == "session.stop":
            return {"type": "session.stop", "payload": {}}

        return None

    def _from_qwen_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        payload = event.get("payload") or {}
        event_type = event.get("type")
        mapping = {
            "server.ready": "session.ready",
            "server.state": "session.state",
            "server.answer_start": "answer.start",
            "server.partial_text": "answer.delta",
            "server.final_text": "answer.done",
            "server.error": "error",
        }
        app_type = mapping.get(event_type)
        if not app_type:
            return None
        return {"type": app_type, "payload": payload}


class OpenAIAdapter(RealtimeAdapter):
    async def run(self, websocket: WebSocket) -> None:
        await send_app_event(websocket, "error", {"message": "OpenAI adapter is not implemented yet."})


class ClaudeAdapter(RealtimeAdapter):
    async def run(self, websocket: WebSocket) -> None:
        await send_app_event(websocket, "error", {"message": "Claude adapter is not implemented yet."})


class GeminiAdapter(RealtimeAdapter):
    async def run(self, websocket: WebSocket) -> None:
        await send_app_event(websocket, "error", {"message": "Gemini Live image input is not compatible with the 4FPS strategy without explicit downgrade."})


def adapter_from_env(provider: str) -> RealtimeAdapter:
    if provider == "local-qwen":
        return LocalQwenAdapter(os.getenv("LOCAL_QWEN_WS_URL", "ws://127.0.0.1:8000/ws/realtime"))
    if provider == "openai":
        return OpenAIAdapter()
    if provider == "claude":
        return ClaudeAdapter()
    if provider == "gemini":
        return GeminiAdapter()
    return LocalQwenAdapter(os.getenv("LOCAL_QWEN_WS_URL", "ws://127.0.0.1:8000/ws/realtime"))
