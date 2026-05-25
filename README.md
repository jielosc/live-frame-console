# Live Frame Console

实时画面问答控制台 — 通过摄像头捕获视频帧，向 AI 后端提问并实时流式返回回答。

本项目不部署模型，仅作为协议转换和 UI 层，将浏览器端的摄像头帧流转发至可插拔的 AI Provider 后端。

## 架构

```
Browser (摄像头 + WebSocket)
    │
    ▼
FastAPI Server (app.py)
    │
    ▼
Adapter (adapters.py)  ──►  AI Provider
  - local-qwen              Qwen 实时 WebSocket 服务
  - openai                   OpenAI 兼容 /v1/chat/completions
  - claude                   (未实现)
  - gemini                   (未实现)
```

前端为纯 HTML/CSS/JS，无构建步骤。后端使用 FastAPI + Uvicorn。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8010
```

浏览器打开 `http://127.0.0.1:8010`（需要摄像头权限，localhost 或 HTTPS 环境）。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `FRAME_APP_PROVIDER` | `local-qwen` | 后端适配器：`local-qwen` / `openai` / `claude` / `gemini` |
| `LOCAL_QWEN_WS_URL` | `ws://127.0.0.1:8000/ws/realtime` | Qwen 上游 WebSocket 地址 |
| `OPENAI_BASE_URL` | `http://192.168.207.214:8000` | OpenAI 兼容 API 地址 |
| `OPENAI_MODEL` | (见源码) | 请求中使用的模型标识 |

也可通过 WebSocket URL 的 `?provider=` 查询参数按连接覆盖 provider。

## 采集策略

| 策略 | 帧率 | 分辨率宽度 | JPEG 质量 | 每次提问最大帧数 |
|---|---|---|---|---|
| `clarity_mode` | 1 FPS | 1280px | 0.72 | 6 |
| `motion_mode` | 4 FPS | 640px | 0.64 | 24 |

`maxFramesPerPrompt` 是应用层的帧预算概念，各 adapter 按自身 API 规格映射（如 Qwen 映射为 `video_max_frames`，OpenAI 映射为 deque 大小）。

## WebSocket 协议

### 客户端 → 服务端

| 事件 | 主要字段 | 说明 |
|---|---|---|
| `session.start` | `strategy`, `maxFramesPerPrompt` | 开始会话 |
| `media.frame` | `imageBase64`, `width`, `height` | 发送一帧 JPEG |
| `prompt.ask` | `text`, `maxNewTokens` | 用户提问 |
| `session.stop` | — | 结束会话 |

### 服务端 → 客户端

| 事件 | 主要字段 | 说明 |
|---|---|---|
| `session.ready` | — | 会话就绪 |
| `session.state` | `frame_count` | 已缓存帧数 |
| `answer.start` | — | 开始流式回答 |
| `answer.delta` | `text` | 回答文本片段 |
| `answer.done` | `text` | 回答完成（全文） |
| `error` | `message` | 错误通知 |

## 添加新 Provider

继承 `RealtimeAdapter`，实现 `run(websocket)` 方法，在 `adapter_from_env()` 中注册即可。

## 依赖

- Python 3.10+
- fastapi, uvicorn, websockets, httpx
