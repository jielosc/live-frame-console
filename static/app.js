(function () {
  const strategies = {
    clarity_mode: { intervalMs: 1000, width: 1280, quality: 0.72, maxFramesPerPrompt: 6 },
    motion_mode: { intervalMs: 250, width: 640, quality: 0.64, maxFramesPerPrompt: 24 },
  };

  const video = document.getElementById("video");
  const empty = document.getElementById("empty");
  const canvas = document.getElementById("canvas");
  const providerEl = document.getElementById("provider");
  const strategyEl = document.getElementById("strategy");
  const statusEl = document.getElementById("status");
  const statsEl = document.getElementById("stats");
  const questionEl = document.getElementById("question");
  const logEl = document.getElementById("log");
  const cameraBtn = document.getElementById("cameraBtn");
  const connectBtn = document.getElementById("connectBtn");
  const stopBtn = document.getElementById("stopBtn");
  const askBtn = document.getElementById("askBtn");

  let stream = null;
  let socket = null;
  let timer = null;
  let busy = false;
  let frameCount = 0;
  let currentAnswer = null;
  let promptSentAtMs = null;
  let ttftBadge = null;

  function strategy() {
    return strategies[strategyEl.value] || strategies.motion_mode;
  }

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function log(role, text) {
    const item = document.createElement("div");
    item.className = `msg ${role}`;
    item.textContent = text;
    logEl.appendChild(item);
    logEl.scrollTop = logEl.scrollHeight;
    return item;
  }

  function updateButtons() {
    const cameraReady = !!stream;
    const connected = socket && socket.readyState === WebSocket.OPEN;
    cameraBtn.disabled = cameraReady;
    connectBtn.disabled = !cameraReady || connected;
    stopBtn.disabled = !cameraReady && !connected;
    askBtn.disabled = !connected;
    providerEl.disabled = connected;
    strategyEl.disabled = connected;
  }

  function wsUrl() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${location.host}/ws/session?provider=${encodeURIComponent(providerEl.value)}`;
  }

  async function startCamera() {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
      audio: false,
    });
    video.srcObject = stream;
    empty.hidden = true;
    setStatus("摄像头已启动");
    updateButtons();
  }

  function stopCapture() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function scheduleCapture(delay) {
    stopCapture();
    timer = setTimeout(async () => {
      await captureFrame();
      if (socket && socket.readyState === WebSocket.OPEN) {
        scheduleCapture(strategy().intervalMs);
      }
    }, delay);
  }

  async function captureFrame() {
    if (busy || !stream || !socket || socket.readyState !== WebSocket.OPEN || video.readyState < 2) {
      return;
    }
    busy = true;
    try {
      const captureStartedAtMs = Date.now();
      const sourceWidth = video.videoWidth || 640;
      const sourceHeight = video.videoHeight || 360;
      const config = strategy();
      const targetHeight = Math.max(1, Math.round(config.width * (sourceHeight / sourceWidth)));
      canvas.width = config.width;
      canvas.height = targetHeight;
      canvas.getContext("2d").drawImage(video, 0, 0, config.width, targetHeight);
      const dataUrl = canvas.toDataURL("image/jpeg", config.quality);
      const captureEncodedAtMs = Date.now();
      socket.send(JSON.stringify({
        type: "media.frame",
        payload: {
          imageBase64: dataUrl.split(",", 2)[1],
          width: config.width,
          height: targetHeight,
          strategy: strategyEl.value,
          captureStartedAtMs,
          captureEncodedAtMs,
          clientSendAtMs: Date.now(),
          captureMs: Math.round((captureEncodedAtMs - captureStartedAtMs) * 10) / 10,
        },
      }));
      frameCount += 1;
      statsEl.textContent = `frames: ${frameCount} | ${strategyEl.value} | ${config.width}px / ${config.intervalMs > 0 ? 1000 / config.intervalMs : 0}FPS`;
    } finally {
      busy = false;
    }
  }

  function connect() {
    socket = new WebSocket(wsUrl());
    setStatus("正在连接");
    updateButtons();

    socket.addEventListener("open", () => {
      const config = strategy();
      frameCount = 0;
      socket.send(JSON.stringify({
        type: "session.start",
        payload: {
          strategy: strategyEl.value,
          maxFramesPerPrompt: config.maxFramesPerPrompt,
        },
      }));
      scheduleCapture(0);
      updateButtons();
    });

    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      const payload = message.payload || {};
      if (message.type === "session.ready") setStatus("会话已连接");
      if (message.type === "session.state" && payload.frame_count != null) setStatus(`缓存帧数 ${payload.frame_count}`);
      if (message.type === "answer.start") {
        const wrapper = log("assistant", "");
        const span = document.createElement("span");
        span.textContent = "...";
        wrapper.appendChild(span);
        currentAnswer = span;
        ttftBadge = null;
      }
      if (message.type === "answer.delta" && currentAnswer) {
        if (!ttftBadge && promptSentAtMs) {
          const ttft = Date.now() - promptSentAtMs;
          const badge = document.createElement("span");
          badge.className = "ttft" + (ttft < 500 ? " good" : ttft < 1500 ? " ok" : " slow");
          badge.textContent = `TTFT: ${ttft}ms`;
          currentAnswer.parentElement.insertBefore(badge, currentAnswer);
          ttftBadge = badge;
        }
        currentAnswer.textContent = payload.text || "";
      }
      if (message.type === "answer.done" && currentAnswer) {
        currentAnswer.textContent = payload.text || "";
        currentAnswer = null;
        promptSentAtMs = null;
      }
      if (message.type === "error") log("error", payload.message || "会话错误");
    });

    socket.addEventListener("close", () => {
      stopCapture();
      socket = null;
      setStatus("会话已断开");
      updateButtons();
    });
  }

  function stop() {
    stopCapture();
    if (socket && socket.readyState !== WebSocket.CLOSED) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "session.stop", payload: {} }));
      }
      socket.close();
      // 状态清理由 close 事件统一处理
    }
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
    stream = null;
    video.srcObject = null;
    empty.hidden = false;
    updateButtons();
  }

  function ask() {
    const text = questionEl.value.trim();
    if (!text || !socket || socket.readyState !== WebSocket.OPEN) return;
    log("user", text);
    promptSentAtMs = Date.now();
    socket.send(JSON.stringify({
      type: "prompt.ask",
      payload: {
        text,
        maxNewTokens: 256,
        clientSentAtMs: promptSentAtMs,
      },
    }));
    questionEl.value = "";
  }

  async function loadProviders() {
    try {
      const resp = await fetch("/api/providers");
      const data = await resp.json();
      (data.providers || []).forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        providerEl.appendChild(opt);
      });
    } catch (e) {
      const opt = document.createElement("option");
      opt.value = "local-qwen";
      opt.textContent = "local-qwen";
      providerEl.appendChild(opt);
    }
  }

  cameraBtn.addEventListener("click", () => startCamera().catch((error) => log("error", error.message || String(error))));
  connectBtn.addEventListener("click", connect);
  stopBtn.addEventListener("click", stop);
  askBtn.addEventListener("click", ask);
  questionEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) ask();
  });
  loadProviders();
  updateButtons();
})();
