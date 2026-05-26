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
  - protocol: ws              Qwen 实时 WebSocket 服务
  - protocol: http             OpenAI 兼容 /v1/chat/completions
```

前端为纯 HTML/CSS/JS，无构建步骤。后端使用 FastAPI + Uvicorn。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 复制配置模板并按需编辑
cp config.yaml.example config.yaml

uvicorn app:app --host 0.0.0.0 --port 8010
```

浏览器打开 `http://127.0.0.1:8010`（需要摄像头权限，localhost 或 HTTPS 环境）。

## 配置

Provider 通过 `config.yaml` 管理（从 `config.yaml.example` 复制）。`config.yaml` 已加入 `.gitignore`，不会提交到仓库。

两种协议路径：

| 协议 | 说明 | 适配器 |
|---|---|---|
| `ws` | WebSocket 双向流（如 Qwen 实时服务） | `LocalQwenAdapter` |
| `http` | OpenAI 兼容 HTTP `/v1/chat/completions` | `OpenAIAdapter` |

### config.yaml 示例

```yaml
default_provider: siliconflow

providers:
  local-qwen:
    protocol: ws
    ws_url: "ws://127.0.0.1:8000/ws/realtime"

  siliconflow:
    protocol: http
    base_url: "https://api.siliconflow.cn"
    model: "Qwen/Qwen3-VL-8B-Instruct"
    api_key: "sk-..."
    max_frames: 24
```

可以添加任意数量的 OpenAI 兼容 provider，自定义名称即可。前端下拉框会自动从 `/api/providers` 读取。

### 配置优先级

1. WebSocket URL `?provider=` 查询参数
2. `config.yaml` 中的 `default_provider`
3. 代码内默认值（`local-qwen`）

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

## API

| 端点 | 说明 |
|---|---|
| `GET /api/providers` | 返回所有已配置的 provider 名称列表 |

## 添加新 Provider

在 `config.yaml` 的 `providers` 下添加条目，设置 `protocol`（`ws` 或 `http`）及对应参数，前端下拉框会自动显示。

## 依赖

- Python 3.10+
- fastapi, uvicorn, websockets, httpx, pyyaml
