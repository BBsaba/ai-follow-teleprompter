"""实时监听：麦克风 → 滑窗 → ASR → 广播。

R2 的定位是「把耳朵接上」，**不参与定位**：
识别结果只作为回显送到控制台，让用户判断「识别得对不对、延迟能不能忍」。
真正把文本变成稿件位置是对齐器（R3）的事。

线程模型：
  · 采集在 PortAudio 线程（回调式，不阻塞）；
  · 推理是 CPU/GPU 密集的，扔进单线程 executor，避免和事件循环抢；
  · 上一次还没跑完就跳过这一拍——宁可丢帧，也不要排队排到十秒前。
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import config, model_finder
from .asr import AsrEngine
from .audio import Recorder, rms


class Listener:
    def __init__(self, broadcast):
        self.engine = AsrEngine()
        self.rec = Recorder()
        self.broadcast = broadcast          # async fn(msg: dict)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="asr")

        self.on = False
        self.loading = False                # 正在加载模型/开麦（首次十几秒）
        self.mic_index = self.rec.device    # 当前用的输入设备（None = 系统默认）
        self._gen = 0                       # 加载代次：用来识别"加载期间用户点了停止"
        self._busy = False
        self._task: asyncio.Task | None = None
        # 识别出文本后的回调（server 里接到对齐器上）。None = 只回显不定位
        self.on_text = None

        self.history: deque[dict] = deque(maxlen=40)
        self.latest = ""
        self.stats = {"ms": 0, "rtf": None, "audio_sec": 0.0, "runs": 0, "skips": 0}
        self.error: str | None = None

    # ---------- 状态 ----------
    def status(self) -> dict:
        return {
            "on": self.on,
            "loading": self.loading,
            "listening": self.on and self.rec.running,
            "mic_index": self.mic_index,
            "level": round(self.rec.level, 4),
            "engine": self.engine.status(),
            "stats": dict(self.stats),
            "latest": self.latest,
            # 最后一次真正识别出文字的时间（unix 秒）。前端靠它判断"到底有没有在听"，
            # 光看 on=true 是分不出"在听"和"在听但一个字没收到"的。
            "last_at": self.history[-1]["t"] if self.history else 0,
            "error": self.error,
        }

    # ---------- 设置 ----------
    def apply_settings(self, asr: dict) -> dict:
        """把设置页的选择落到采集器与引擎上。

        只在**没开麦**时有意义（服务端会先拦一道 409）。
        引擎那边只改参数不主动加载，所以这个函数是毫秒级的——
        不能让"保存设置"这个动作把界面卡住十几秒。
        """
        mic = asr.get("mic_index")
        mic_changed = mic != self.mic_index
        if mic_changed:
            self.rec.set_device(mic)
            self.mic_index = mic

        model_changed = self.engine.reconfigure(
            model_dir=asr.get("model_dir"),
            device=asr.get("device"),
            dtype=asr.get("dtype"),
        )
        return {"mic_changed": mic_changed, "model_changed": model_changed}

    # ---------- 开关 ----------
    async def start(self) -> None:
        """开麦。首次会加载模型（十几秒），期间 loading=True 且持续广播状态。

        加载是必须让用户看见的：AI 跟随模式下点开始，如果界面只显示"跟读中"
        却十几秒不动，用户会以为坏了——这正是早先版本踩的坑。
        """
        if self.on or self.loading:
            return
        self._gen += 1
        gen = self._gen
        self.loading = True
        self.error = None
        await self.broadcast({"type": "asr", "asr": self.status()})
        try:
            await asyncio.get_running_loop().run_in_executor(self.pool, self._open)
        except model_finder.ModelMissing as e:
            # 「模型没下载 / 放错文件夹」是最高频的首次使用问题。
            # 界面侧栏窄，只放两行短提示；完整说明（找过哪些目录、怎么解决）打到终端。
            self.rec.close()
            if gen == self._gen:
                self.loading = False
                self.error = e.user_msg
                print("\n" + str(e) + "\n", flush=True)
                await self.broadcast({"type": "asr", "asr": self.status()})
            return
        except Exception as e:
            self.rec.close()                # 兜底：_open 里可能已关，重复调用无副作用
            if gen == self._gen:            # 期间没被停止，才报这个错
                self.loading = False
                self.error = f"麦克风或模型加载失败：{e}"
                await self.broadcast({"type": "asr", "asr": self.status()})
            return
        if gen != self._gen:
            # 加载到一半用户点了停止：麦克风可能已经被打开了，收掉，别偷偷在听
            self.rec.close()
            return
        self.loading = False
        self.on = True
        self.error = None
        self._task = asyncio.create_task(self._loop())
        await self.broadcast({"type": "asr", "asr": self.status()})

    def _open(self) -> None:
        # 先开麦、再加载模型（顺序是刻意的）。
        # 加载要十来秒，用户点完开始往往就开念了；如果先加载后开麦，
        # 这十几秒的声音一个字节都收不到，引擎起来时用户已经念完一句 ——
        # 表现就是"我明明念了，它一点反应都没有"。先开麦就能把这段声音
        # 留在环形缓冲里，加载完第一拍直接识别最近几秒。
        self.rec.open()
        try:
            self.engine.load()
        except Exception:
            self.rec.close()     # 模型没起来就别留着麦克风空转
            raise

    async def stop(self) -> None:
        self._gen += 1                  # 让正在飞的那次加载失效
        self.on = False
        self.loading = False
        if self._task:
            self._task.cancel()
            self._task = None
        self.rec.close()
        await self.broadcast({"type": "asr", "asr": self.status()})

    async def toggle(self) -> None:
        await (self.stop() if self.on else self.start())

    # ---------- 主循环 ----------
    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        hop = float(config.ASR["hop_sec"])
        win = float(config.ASR["window_sec"])
        gate = float(config.ASR["rms_gate"])
        min_speech = float(config.ASR["min_speech_sec"])

        while self.on:
            # 节拍按「开始到开始」算：只在末尾补足剩余时间。
            # 原来是「先睡 hop 再干活」，等于每拍多花一个 hop ——
            # GPU 上推理只要 0.25 s，却因为白睡 0.5 s 变成 1.3 Hz。
            t_start = time.perf_counter()
            try:
                wav = self.rec.tail(win)
                # VU 一直推，让用户知道麦克风通不通
                await self.broadcast({"type": "vu", "level": round(self.rec.level, 4),
                                      "rms": round(rms(wav), 5)})
                if wav.size < min_speech * 16000 or rms(wav) < gate or self._busy:
                    self.stats["skips"] += 1
                    continue

                self._busy = True
                t0 = time.perf_counter()
                text = await loop.run_in_executor(self.pool, self._run, wav)
                dt = time.perf_counter() - t0
                self._busy = False

                self.stats["runs"] += 1
                self.stats["ms"] = int(dt * 1000)
                self.stats["audio_sec"] = round(wav.size / 16000, 2)
                self.stats["rtf"] = round(dt / (wav.size / 16000), 3)

                if text and text != self.latest:
                    self.latest = text
                    self.history.append({"t": round(time.time(), 2), "text": text,
                                         "ms": self.stats["ms"]})
                await self.broadcast({
                    "type": "asr",
                    "asr": self.status(),
                    "text": text,
                })

                # 回显完之后再驱动位置：先让用户看到"听到了什么"，
                # 位置动得对不对才解释得清
                if text and self.on_text:
                    await self.on_text(text)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._busy = False
                self.error = f"{type(e).__name__}: {e}"
                await self.broadcast({"type": "asr", "asr": self.status()})
            finally:
                # 推理慢的话已经超时了，就不再睡（否则等于人为降频）
                spent = time.perf_counter() - t_start
                if spent < hop and self.on:
                    await asyncio.sleep(hop - spent)

    def _run(self, wav: np.ndarray) -> str:
        return self.engine.transcribe(wav, 16000)

    # ---------- 自检 ----------
    async def selftest(self) -> dict:
        """拿仓库里的样例音频跑一遍，确认模型在本机能跑。

        不碰麦克风——用户可能正戴着耳机不方便说话，也可能环境太吵。
        顺带把模型加载好，之后开麦就是秒开。
        """
        import wave

        p = config.ROOT / "tests" / "fixtures" / "asr_zh.wav"
        if not p.exists():
            return {"ok": False, "error": f"找不到自检音频 {p}"}
        try:
            with wave.open(str(p)) as w:
                sr = w.getframerate()
                x = np.frombuffer(w.readframes(w.getnframes()),
                                  dtype=np.int16).astype(np.float32) / 32768.0
            loop = asyncio.get_running_loop()
            t0 = time.perf_counter()
            text = await loop.run_in_executor(self.pool, self._run, x)
            wall = time.perf_counter() - t0
            sec = len(x) / sr
            self.latest = text
            await self.broadcast({"type": "asr", "asr": self.status(), "text": text})
            # 首次调用会把模型加载时间算进 wall，所以推理耗时取 engine 自己记的纯推理值
            infer_ms = self.engine.last_ms or int(wall * 1000)
            return {
                "ok": True,
                "text": text,
                "ms": infer_ms,
                "wall_ms": int(wall * 1000),
                "load_ms": self.engine.load_ms,
                "audio_sec": round(sec, 2),
                "rtf": round(infer_ms / 1000 / sec, 3),
            }
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            return {"ok": False, "error": self.error}
