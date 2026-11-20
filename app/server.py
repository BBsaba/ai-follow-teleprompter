"""FastAPI 服务：静态页 + 稿件 API + 状态 API + WebSocket 广播。"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import audio, config, model_finder, shutdown, storage, store
from .listener import Listener
from .session import Session


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, msg: dict) -> None:
        if not self.clients:
            return
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


hub = Hub()
state = store.load_state()
session = Session(state["ui"], store.read_script(state["last_script_id"]))
listener = Listener(hub.broadcast)
# 把上次存下来的麦克风/模型选择装回去（此时还没开麦，纯赋值，不加载模型）
listener.apply_settings(state["asr"])


async def _on_asr_text(text: str) -> None:
    """识别结果 → 对齐器 → 位置。

    独立成一个函数而不是塞进 Listener，是为了让 Listener 保持"只管听"，
    不至于把稿件状态也拖进音频循环里（R6 要加冷却与重锚，到时只改这里）。
    """
    msg = session.feed_asr(text)
    if msg:
        await hub.broadcast(msg)


listener.on_text = _on_asr_text


async def _ensure_ear() -> None:
    """AI 跟随必须有耳朵：开录时麦克风还没开，就自己开。

    ⛔ 这是修一个真实缺陷，不是加便利功能。早先版本 `start` 只把会话状态
    改成 RUNNING 就完事，`listener` 完全没被碰 —— 用户在 AI 跟随模式下按开始，
    界面显示"跟读中"，但实际上没有任何东西在听，稿子一动不动，
    并且和"开麦"按钮那次不同，连一句加载提示都没有。表现就是"AI 根本不跟随"。

    不 await 是刻意的：加载模型要十几秒，await 会把这条 WS 消息挂住，
    前端按钮会卡在按下状态。状态由 listener 自己持续广播。
    """
    if listener.on or listener.loading:
        return
    asyncio.create_task(listener.start())


def _quiet_disconnect(loop, context):
    """Windows 上客户端硬断连（关窗口 / 拔网线 / 休眠）会抛这个，
    是 ProactorEventLoop 在 shutdown 已重置的 socket，与服务本身无关。
    默认处理会往 stderr 喷一大段 Traceback，用户会以为程序崩了——这里吞掉。"""
    exc = context.get("exception")
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (10054, 995):
        return
    msg = str(context.get("message", ""))
    if "socket.send() raised exception" in msg or "_call_connection_lost" in msg:
        return
    loop.default_exception_handler(context)


async def _ticker() -> None:
    last = time.perf_counter()
    interval = 1.0 / config.TICK_HZ
    while True:
        await asyncio.sleep(interval)
        now = time.perf_counter()
        dt = now - last
        last = now
        msg = session.tick(dt)
        if msg:
            await hub.broadcast(msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.get_running_loop().set_exception_handler(_quiet_disconnect)
    store.seed()
    # 模块导入时可能还没有稿件文件，这里补一次装载
    session.rebuild(store.read_script(state["last_script_id"]))
    task = asyncio.create_task(_ticker())
    try:
        yield
    finally:
        task.cancel()
        await listener.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.WEB_DIR)), name="static")


# ---------------- 页面 ----------------
def _app_version() -> str:
    """版本号只有一个真源：安装目录里的 `VERSION.txt`（构建脚本写的）。

    前端别再硬编码一份 —— 那样每次发版要记得改两处，迟早出现
    「界面写着 2.2.2、实际装的是 2.2.3」这种对不上的情况。
    源码目录里没有这个文件，就报 dev。
    """
    try:
        first = (config.ROOT / "VERSION.txt").read_text(encoding="utf-8").splitlines()[0]
        return first.split()[-1]            # "AITeleprompter 2.2.3" -> "2.2.3"
    except Exception:
        return "dev"


@app.get("/api/version")
async def api_version():
    return {"version": _app_version()}


@app.get("/")
async def page_root():
    return FileResponse(config.WEB_DIR / "console.html")


@app.get("/console")
async def page_console():
    return FileResponse(config.WEB_DIR / "console.html")


@app.get("/prompter")
async def page_prompter():
    return FileResponse(config.WEB_DIR / "prompter.html")


@app.get("/settings")
async def page_settings():
    return FileResponse(config.WEB_DIR / "settings.html")


# ---------------- 稿件 ----------------
@app.get("/api/scripts")
async def api_scripts():
    store.seed()
    return {"items": store.list_scripts(), "current": state.get("last_script_id")}


@app.get("/api/scripts/{sid}")
async def api_script(sid: str):
    return {"id": sid, "text": store.read_script(sid)}


@app.post("/api/scripts")
async def api_save_script(body: dict):
    sid = (body.get("id") or state.get("last_script_id") or "untitled").strip()
    if not store.is_valid_sid(sid):
        return JSONResponse({"ok": False, "error": "稿件名不合法（不能含 / \\ : * ? 等字符）"},
                            status_code=400)
    text = body.get("text", "")
    store.write_script(sid, text)
    state["last_script_id"] = sid
    store.save_state(state)
    session.rebuild(text)
    await hub.broadcast({"type": "script", "script": session.script.to_dict()})
    await hub.broadcast({"type": "pos", "pos": session.snapshot()})
    return {
        "id": sid,
        "chars": len(session.script.chars),
        "n_lines": len(session.script.lines),
    }


@app.delete("/api/scripts/{sid}")
async def api_delete_script(sid: str):
    """删稿件。删掉的正好是当前这篇时，自动切到剩下的第一篇。"""
    if not store.is_valid_sid(sid):
        return JSONResponse({"ok": False, "error": "稿件名不合法"}, status_code=400)
    if session.state != "IDLE":
        # 录制中删稿会让正在念的内容瞬间失效，先停下再说
        return JSONResponse({"ok": False, "error": "录制中不能删除稿件，请先按 Esc 退出"},
                            status_code=409)

    existed = store.delete_script(sid)
    store.seed()                       # 删光了就把示例稿补回来，界面不至于空着
    items = store.list_scripts()

    if state.get("last_script_id") == sid and items:
        state["last_script_id"] = items[0]["id"]
        store.save_state(state)
        session.rebuild(store.read_script(state["last_script_id"]))
        await hub.broadcast({"type": "script", "script": session.script.to_dict()})
        await hub.broadcast({"type": "pos", "pos": session.snapshot()})

    return {"ok": existed, "items": items,
            "current": state.get("last_script_id"),
            "text": store.read_script(state.get("last_script_id") or "")}


# ---------------- 设置：麦克风 / 模型 / 推理 ----------------
def _settings_payload() -> dict:
    return {
        "asr": dict(state["asr"]),
        "devices": audio.list_inputs(),
        "models": model_finder.scan(),
        "default_model": str(model_finder.default_dir()),
        "engine": listener.engine.status(),
        # 正在用麦克风时不给改——否则等于录到一半把话筒拔了
        "busy": bool(listener.on or listener.loading),
    }


def _normalize_asr(patch: dict) -> tuple[dict, str | None]:
    """把前端传来的东西收拾干净：能转的转，越界的报错。

    返回 (要写入的字段, 错误文案)。错误文案是 None 表示通过。
    """
    out: dict = {}

    if "mic_index" in patch:
        v = patch["mic_index"]
        if v in (None, ""):
            out["mic_index"] = None              # 回到系统默认输入
        else:
            try:
                v = int(v)
            except (TypeError, ValueError):
                return out, f"麦克风编号无效：{v!r}"
            ids = {d["id"] for d in audio.list_inputs()}
            if v not in ids:
                return out, f"找不到编号 {v} 的输入设备（可用：{sorted(ids)}）"
            out["mic_index"] = v

    if "model_dir" in patch:
        v = str(patch["model_dir"] or "").strip()
        if not v:
            out["model_dir"] = None              # None = 自动在 models/ 里找
        else:
            p = Path(v).expanduser()
            if not model_finder.is_model_dir(p):
                return out, (
                    f"这个目录不像模型：{p}\n"
                    "必须同时有 config.json 和 model.safetensors（或 pytorch_model.bin）"
                )
            out["model_dir"] = str(p)

    for key, allowed in config.ASR_CHOICES.items():
        if key in patch:
            if patch[key] not in allowed:
                return out, f"{key} 只能是 {' / '.join(allowed)}"
            out[key] = patch[key]

    return out, None


@app.get("/api/settings")
async def api_get_settings():
    return _settings_payload()


@app.get("/api/devices")
async def api_devices():
    """单独列出输入设备，设置页「刷新」按钮用。"""
    return {"devices": audio.list_inputs()}


@app.get("/api/models")
async def api_models():
    """扫 models/ 下所有能认出来的模型目录。"""
    return {"models": model_finder.scan(),
            "default": str(model_finder.default_dir())}


@app.post("/api/mic/test")
async def api_mic_test(body: dict | None = None):
    """试一下这个麦克风有没有声音。

    要真等 1.2 秒，所以丢进线程池——直接在事件循环里 sleep 会把整个服务卡住。
    """
    if listener.on or listener.loading:
        return JSONResponse({"error": "麦克风正在用，先停止识别再试"}, status_code=409)
    body = body or {}
    idx = body.get("index", state["asr"].get("mic_index"))
    if idx == "":
        idx = None
    try:
        idx = None if idx is None else int(idx)
    except (TypeError, ValueError):
        return JSONResponse({"error": f"麦克风编号无效：{idx!r}"}, status_code=400)
    ms = max(300, min(5000, int(body.get("ms") or 1200)))
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, audio.probe_input, idx, ms)


@app.put("/api/settings")
async def api_put_settings(patch: dict):
    if listener.on or listener.loading:
        return JSONResponse(
            {"error": "麦克风正在用，先停止识别再改设置"}, status_code=409)

    norm, err = _normalize_asr(patch)
    if err:
        return JSONResponse({"error": err}, status_code=400)

    state["asr"].update(norm)
    changed = listener.apply_settings(state["asr"])
    store.save_state(state)

    payload = _settings_payload()
    payload["changed"] = changed
    await hub.broadcast({"type": "settings", "asr": state["asr"]})
    return payload


# ---------------- 磁盘占用 ----------------
#: 统计和清理都要走文件系统，放线程池跑：模型目录几万个文件，在事件循环里数
#: 会把 60 Hz 的心跳（_ticker）整个卡住，表现为跟读画面一顿一顿的。
@app.get("/api/storage")
async def api_storage():
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, storage.scan)


@app.post("/api/storage/clean")
async def api_storage_clean(body: dict | None = None):
    """清日志 / 清安装缓存。

    ⛔ 只认 `storage.CLEANERS` 这张表。传 `what=scripts` 会拿到 400 ——
    稿件是用户资产，这个接口**永远不该有删除它的能力**，白名单比黑名单可靠：
    将来有人往 storage 里加了新函数，也不会因为漏配一个 `if` 就变成可远程调用的删除器。
    """
    what = str((body or {}).get("what") or "").strip()
    fn = storage.CLEANERS.get(what)
    if fn is None:
        return JSONResponse({"ok": False, "error": f"不能清理这类东西：{what!r}"},
                            status_code=400)
    loop = asyncio.get_running_loop()
    did = await loop.run_in_executor(None, fn)
    after = await loop.run_in_executor(None, storage.scan)
    return {"ok": not did["failed"], "did": did, "storage": after}


# ---------------- 状态 ----------------
@app.get("/api/state")
async def api_state():
    return {
        "ui": state["ui"],
        "last_script_id": state.get("last_script_id"),
        "script": session.script.to_dict(),
    }


@app.put("/api/state")
async def api_put_state(patch: dict):
    ui = state["ui"]
    before_per = int(ui["per_line"])
    before_mode = session.mode
    for k, v in patch.items():
        if k in config.DEFAULT_UI:
            ui[k] = v
    store.save_state(state)

    if session.mode != before_mode:
        session.on_mode_changed()

    if int(ui["per_line"]) != before_per:
        session.rebuild()
        await hub.broadcast({"type": "script", "script": session.script.to_dict()})
    await hub.broadcast({"type": "ui", "ui": ui})
    return {"ui": ui, "mode": session.mode}


# ---------------- 语音识别 ----------------
@app.get("/api/asr")
async def api_asr():
    return listener.status()


@app.post("/api/asr")
async def api_asr_toggle():
    await listener.toggle()
    return listener.status()


@app.post("/api/asr/selftest")
async def api_asr_selftest():
    return await listener.selftest()


# ---------------- 退出程序 ----------------
@app.post("/api/quit")
async def api_quit(background: BackgroundTasks):
    """停掉服务和整个进程。

    为什么需要这个接口：快捷方式用 `pythonw.exe` 启动，**没有控制台窗口**，
    用户关掉浏览器标签页之后服务还在后台跑，想停只能去任务管理器里找
    `pythonw.exe` 结束掉 —— 那不是正常用户该做的事。这个按钮替掉那一步。

    ⚠️ 用 BackgroundTasks 而不是直接调：Starlette 保证后台任务在**响应发完
    之后**才跑。早先直接调过一次，实测服务退得太快，连接被掐断，浏览器只拿到
    一个网络错误 —— 用户点完按钮看到「出错了」，还以为没退成功。
    """
    background.add_task(shutdown.request_quit)
    return {"ok": True, "quitting": True}


# ---------------- WebSocket ----------------
async def _dispatch(msg: dict) -> None:
    t = msg.get("type")
    if t == "start":
        session.start()
        # AI 跟随没有麦克风就是块死画面，所以开始录制时把耳朵一并接上
        if session.mode == "ai":
            await _ensure_ear()
    elif t == "stop":
        session.stop()
    elif t in ("pause", "resume"):
        session.toggle_pause()
    elif t == "wheel":
        session.wheel(int(msg.get("delta", 0)))
    elif t == "asr":
        await listener.toggle()
        return
    else:
        return
    await hub.broadcast({"type": "pos", "pos": session.snapshot()})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        await ws.send_json(
            {
                "type": "init",
                "script": session.script.to_dict(),
                "ui": state["ui"],
                "pos": session.snapshot(),
                "asr": listener.status(),
            }
        )
        while True:
            msg = await ws.receive_json()
            await _dispatch(msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.clients.discard(ws)
