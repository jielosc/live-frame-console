from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from typing import Any

import httpx
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from config import get_provider_config


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
    def __init__(self, base_url: str, model: str, max_frames: int = 24) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_frames = max_frames

    async def run(self, websocket: WebSocket) -> None:
        frames: deque[dict[str, Any]] = deque(maxlen=self.max_frames)
        try:
            while True:
                raw = await websocket.receive_text()
                event = json.loads(raw)
                event_type = event.get("type")
                payload = event.get("payload") or {}

                if event_type == "session.start":
                    budget = int(payload.get("maxFramesPerPrompt") or self.max_frames)
                    frames = deque(maxlen=budget)
                    await send_app_event(websocket, "session.ready", {})

                elif event_type == "media.frame":
                    frames.append(payload)

                elif event_type == "prompt.ask":
                    text = payload.get("text") or ""
                    await self._ask(websocket, text, list(frames), payload)

                elif event_type == "session.stop":
                    return

        except WebSocketDisconnect:
            return
        except Exception as exc:
            await send_app_event(websocket, "error", {"message": f"OpenAI adapter error: {exc}"})

    async def _ask(self, websocket: WebSocket, text: str, frame_list: list[dict[str, Any]], payload: dict[str, Any]) -> None:
        content: list[dict[str, Any]] = []
        for frame in frame_list:
            b64 = frame.get("imageBase64") or ""
            if b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })
        content.append({"type": "text", "text": text})

        messages = [{"role": "user", "content": content}]
        max_tokens = int(payload.get("maxNewTokens") or 256)

        await send_app_event(websocket, "answer.start", {})

        collected = ""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "stream": True,
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        chunk = json.loads(data)
                        delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                        token = delta.get("content") or ""
                        if token:
                            collected += token
                            await send_app_event(websocket, "answer.delta", {"text": collected})
        except Exception as exc:
            await send_app_event(websocket, "error", {"message": f"LLM request failed: {exc}"})
            return

        await send_app_event(websocket, "answer.done", {"text": collected})


class ClaudeAdapter(RealtimeAdapter):
    async def run(self, websocket: WebSocket) -> None:
        await send_app_event(websocket, "error", {"message": "Claude adapter is not implemented yet."})


class GeminiAdapter(RealtimeAdapter):
    async def run(self, websocket: WebSocket) -> None:
        await send_app_event(websocket, "error", {"message": "Gemini Live image input is not compatible with the 4FPS strategy without explicit downgrade."})


def adapter_from_env(provider: str) -> RealtimeAdapter:
    cfg = get_provider_config(provider)

    if provider == "local-qwen":
        return LocalQwenAdapter(url=cfg["ws_url"])
    if provider == "openai":
        return OpenAIAdapter(
            base_url=cfg["base_url"],
            model=cfg["model"],
            max_frames=cfg["max_frames"],
        )
    if provider == "claude":
        return ClaudeAdapter()
    if provider == "gemini":
        return GeminiAdapter()

    fallback = get_provider_config("local-qwen")
    return LocalQwenAdapter(url=fallback["ws_url"])
