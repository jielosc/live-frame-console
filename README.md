# Realtime Frame App

Minimal application layer for testing two live frame upload strategies. It does not deploy a model; it talks to provider adapters.

## Run

Start the existing local Qwen service first:

```bash
cd /home/lrt/local-model-serving
conda run -n qwen3vl python api_server.py --host 0.0.0.0 --port 8000
```

Run this app:

```bash
cd /home/lrt/realtime-frame-app
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8010
```

Open:

```text
http://127.0.0.1:8010
```

## Strategies

- `clarity_mode`: 1FPS, width `1280`, JPEG quality `0.72`, `maxFramesPerPrompt=6`.
- `motion_mode`: 4FPS, width `640`, JPEG quality `0.64`, `maxFramesPerPrompt=24`.

`maxFramesPerPrompt` is an app-level frame budget. The local Qwen adapter maps it to `video_max_frames`; commercial adapters must map it according to their own API shape.

## Providers

Default provider:

```bash
FRAME_APP_PROVIDER=local-qwen
LOCAL_QWEN_WS_URL=ws://127.0.0.1:8000/ws/realtime
```

Implemented:

- `local-qwen`: forwards the app protocol to the existing `/ws/realtime` service.

Skeleton only:

- `openai`
- `claude`
- `gemini`

Gemini Live image input is not compatible with the 4FPS strategy unless an adapter explicitly rejects or downgrades that strategy.

## App WebSocket Protocol

Client events:

- `session.start`
- `media.frame`
- `prompt.ask`
- `session.stop`

Server events:

- `session.ready`
- `session.state`
- `answer.start`
- `answer.delta`
- `answer.done`
- `error`
