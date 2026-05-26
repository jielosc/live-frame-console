from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH = _ROOT / "config.yaml"

# In-memory config dict, loaded once at import time.
_cfg: dict[str, Any] = {}

if _CONFIG_PATH.exists():
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        _cfg = yaml.safe_load(f) or {}


def get_default_provider() -> str:
    return os.getenv("FRAME_APP_PROVIDER") or _cfg.get("default_provider") or "local-qwen"


def get_provider_config(provider: str) -> dict[str, Any]:
    """Return merged config for *provider*: config.yaml values overridden by env vars."""
    section: dict[str, Any] = (_cfg.get("providers") or {}).get(provider) or {}

    if provider == "local-qwen":
        return {
            "ws_url": os.getenv("LOCAL_QWEN_WS_URL") or section.get("ws_url") or "ws://127.0.0.1:8000/ws/realtime",
        }

    if provider == "openai":
        return {
            "base_url": os.getenv("OPENAI_BASE_URL") or section.get("base_url") or "http://127.0.0.1:8000",
            "model": os.getenv("OPENAI_MODEL") or section.get("model") or "Qwen2.5-VL-7B-Instruct",
            "api_key": os.getenv("OPENAI_API_KEY") or section.get("api_key") or "",
            "max_frames": int(os.getenv("OPENAI_MAX_FRAMES") or section.get("max_frames") or 24),
        }

    if provider == "claude":
        return {
            "api_key": os.getenv("CLAUDE_API_KEY") or section.get("api_key") or "",
        }

    if provider == "gemini":
        return {
            "api_key": os.getenv("GEMINI_API_KEY") or section.get("api_key") or "",
        }

    return section
