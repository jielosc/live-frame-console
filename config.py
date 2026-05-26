from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH = _ROOT / "config.yaml"

_cfg: dict[str, Any] = {}

if _CONFIG_PATH.exists():
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        _cfg = yaml.safe_load(f) or {}


def get_default_provider() -> str:
    return os.getenv("FRAME_APP_PROVIDER") or _cfg.get("default_provider") or "local-qwen"


def get_all_provider_names() -> list[str]:
    return list((_cfg.get("providers") or {}).keys())


def get_provider_protocol(provider: str) -> str:
    section: dict[str, Any] = (_cfg.get("providers") or {}).get(provider) or {}
    proto = section.get("protocol")
    if proto in ("ws", "http"):
        return proto
    # backward compat: "openai" name without protocol defaults to http
    if provider == "openai":
        return "http"
    # "local-qwen" without protocol defaults to ws
    if provider == "local-qwen":
        return "ws"
    return "http"


def get_provider_config(provider: str) -> dict[str, Any]:
    """Return config for *provider* with sensible defaults."""
    section: dict[str, Any] = (_cfg.get("providers") or {}).get(provider) or {}
    return {
        "protocol": get_provider_protocol(provider),
        "ws_url": section.get("ws_url") or "ws://127.0.0.1:8000/ws/realtime",
        "base_url": section.get("base_url") or "http://127.0.0.1:8000",
        "model": section.get("model") or "",
        "api_key": section.get("api_key") or "",
        "max_frames": int(section.get("max_frames") or 24),
    }
