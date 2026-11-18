"""手动验证 ASR：拿官方样例 wav 跑一遍，打印识别结果与 RTF。

不放进自动化测试套件——它要加载 1.8 GB 权重，跑一次几十秒。

用法：
    python tests/try_asr.py
    python tests/try_asr.py tests/fixtures/asr_zh.wav
"""
from __future__ import annotations

import os
import sys
import time
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path) as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    if w.getsampwidth() != 2:
        raise SystemExit("只支持 16-bit PCM wav")
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def main() -> int:
    rel = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/asr_zh.wav"
    path = rel if os.path.isabs(rel) else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel)

    t0 = time.perf_counter()
    from app.asr import AsrEngine
    print(f"import  {time.perf_counter() - t0:.1f}s", flush=True)

    x, sr = read_wav(path)
    dur = len(x) / sr
    print(f"音频    {os.path.basename(path)}  {dur:.2f}s @ {sr} Hz", flush=True)

    eng = AsrEngine()
    t0 = time.perf_counter()
    eng.load()
    print(f"加载    {eng.load_ms} ms  device={eng.device} dtype={eng.dtype_name}", flush=True)
    print(f"首次总等待 {time.perf_counter() - t0:.1f}s", flush=True)

    for i in range(2):
        t0 = time.perf_counter()
        txt = eng.transcribe(x, sr)
        dt = time.perf_counter() - t0
        print(f"[{i + 1}] {eng.last_ms:5d} ms   RTF={dt / dur:.3f}   {txt}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
