"""麦克风采集：16 kHz 单声道环形缓冲。

设计要点：
  · 采集在 PortAudio 自己的线程里跑（回调式），主线程只读快照，绝不阻塞音频回调；
  · 缓冲按「秒」保留，ASR 要哪一段就切哪一段，不做流式状态机（R2 先准离线跑通）；
  · 采样率优先直接要 16 kHz —— WASAPI/MME 会自己做重采样；要不到就退回设备默认率，
    再用 numpy 线性重采样。宁可音质差一点，也不能在用户机器上打不开。
"""
from __future__ import annotations

import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd

from . import config


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or x.size == 0:
        return x
    n = int(round(x.size * dst / src))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    # 线性插值足够：ASR 前端本来就要做 mel 滤波，48k→16k 的线性误差可以忽略
    xp = np.linspace(0.0, 1.0, x.size, endpoint=False)
    fp = np.linspace(0.0, 1.0, n, endpoint=False)
    return np.interp(fp, xp, x).astype(np.float32)


class Recorder:
    def __init__(self, keep_sec: float = 30.0, device=None):
        self.sr = int(config.AUDIO["sr"])
        self.channels = int(config.AUDIO["channels"])
        self.keep = keep_sec
        # device 为 None = 系统默认输入；设置页选了具体设备就传索引进来
        self.device = device if device is not None else config.AUDIO["device"]

        self._buf: deque[np.ndarray] = deque()
        self._n = 0
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._dev_sr = self.sr

        self.level = 0.0          # 0..1，给 VU 条用
        self.last_error: str | None = None

    # ---------- 生命周期 ----------
    @property
    def running(self) -> bool:
        return self._stream is not None

    def open(self) -> None:
        if self._stream is not None:
            return
        block = int(self.sr * config.AUDIO["block_ms"] / 1000)
        try:
            self._open_at(self.sr, block)
        except Exception:
            # 设备不接受 16 kHz，就用它自己的默认率
            info = sd.query_devices(self.device, "input")
            self._dev_sr = int(info["default_samplerate"])
            self._open_at(self._dev_sr, int(self._dev_sr * config.AUDIO["block_ms"] / 1000))
        self._stream.start()

    def _open_at(self, sr: int, block: int) -> None:
        self._stream = sd.InputStream(
            samplerate=sr,
            blocksize=block,
            channels=self.channels,
            dtype="float32",
            device=self.device,
            callback=self._cb,
        )
        self._n = 0
        with self._lock:
            self._buf.clear()

    def close(self) -> None:
        s, self._stream = self._stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass

    def set_device(self, device) -> None:
        """换麦克风。先把现有流关掉，下次 open() 用新设备。

        不在跑的时候调用是零成本的；正在跑的话调用方要先停（服务端会拦）。
        """
        self.close()
        self.device = device if device is not None else config.AUDIO["device"]
        self.last_error = None
        self.level = 0.0

    # ---------- 回调 ----------
    def _cb(self, indata, frames, time_info, status) -> None:
        if status:
            self.last_error = str(status)
        x = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        with self._lock:
            self._buf.append(x)
            self._n += x.size
            limit = int(self.keep * self._dev_sr)
            while self._buf and self._n - self._buf[0].size >= limit:
                self._n -= self._buf.popleft().size
        # 峰值电平，指数衰减，给 VU 用
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        self.level = max(peak, self.level * 0.82)

    # ---------- 读取 ----------
    def tail(self, seconds: float) -> np.ndarray:
        """最近 seconds 秒的音频（16 kHz）。不足就返回现有的。"""
        with self._lock:
            if not self._buf:
                return np.zeros(0, dtype=np.float32)
            want = int(seconds * self._dev_sr)
            chunks: list[np.ndarray] = []
            got = 0
            for blk in reversed(self._buf):
                chunks.append(blk)
                got += blk.size
                if got >= want:
                    break
        x = np.concatenate(chunks[::-1])
        if x.size > want:
            x = x[-want:]
        return _resample(x, self._dev_sr, self.sr)

    def take(self, seconds: float) -> np.ndarray:
        """切走最近 seconds 秒（用于增量推理后清空，避免重复识别）。"""
        return self.tail(seconds)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
            self._n = 0


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def list_inputs() -> list[dict]:
    """所有能录的输入设备。设置页的下拉用这个。

    顺手标出「哪个是系统默认」——用户经常不知道该选哪个，
    而选错的后果是"程序在听，但听到的是静音"。
    """
    out: list[dict] = []
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = -1
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                out.append({
                    "id": i,
                    "name": d["name"],
                    "channels": int(d["max_input_channels"]),
                    "sr": int(d["default_samplerate"] or 0),
                    "default": i == default_in,
                })
    except Exception:
        pass
    return out


def probe_input(device, ms: int = 1200) -> dict:
    """开一次临时流，测这个设备到底有没有声音。设置页「试一下」按钮用。

    用户选错麦克风时，界面上「在听」和「没声音」长得一模一样，
    所以让他当场看到电平跳动，比事后排查省事得多。
    """
    peak = 0.0

    def cb(indata, frames, time_info, status) -> None:
        nonlocal peak
        if indata.size:
            peak = max(peak, float(np.max(np.abs(indata))))

    sr = 0
    try:
        info = sd.query_devices(device, "input")
        sr = int(info["default_samplerate"] or 16000)
        with sd.InputStream(samplerate=sr, blocksize=max(64, int(sr * 0.05)),
                            channels=1, dtype="float32", device=device,
                            callback=cb):
            time.sleep(ms / 1000)
    except Exception as e:
        return {"ok": False, "error": str(e), "level": 0.0, "sr": sr}
    return {"ok": True, "error": None, "level": round(peak, 4), "sr": sr}


def now_ms() -> int:
    return int(time.time() * 1000)
