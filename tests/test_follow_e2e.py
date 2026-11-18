"""端到端：样例音频 → ASR → 对齐 → 位置。

不需要麦克风，也不需要模型之外的东西：
用仓库里的 4.2 秒样例音频跑一次真实识别，再喂给对齐器，看位置对不对。

    python tests/test_follow_e2e.py

会加载模型（首次十几秒），所以默认不放进快速测试集。
"""
import statistics
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from app import model_finder
from app.align import Aligner
from app.script import Script

OK = 0
FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


def load_wav(p: Path) -> np.ndarray:
    with wave.open(str(p)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    assert sr == 16000, f"样例音频应为 16 kHz，实际 {sr}"
    return x.astype(np.float32) / 32768.0


def main():
    fx = ROOT / "tests" / "fixtures" / "asr_zh.wav"
    if not fx.exists():
        print(f"[跳过] 找不到 {fx}")
        return 0
    found, _ = model_finder.find()
    if found is None:
        print(f"[跳过] 模型未下载（在 models/ 里没找到）")
        print("       跑 python tools/download_model.py 之后再来")
        return 0

    from app.asr import AsrEngine

    wav = load_wav(fx)
    print(f"[音频] {len(wav) / 16000:.2f} s @ 16000 Hz")

    eng = AsrEngine()
    t0 = time.perf_counter()
    eng.load()
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"[模型] {eng.status()['device']} · {eng.status()['dtype']} · 加载 {load_ms:.0f} ms")

    t1 = time.perf_counter()
    text = eng.transcribe(wav, 16000)
    infer_ms = eng.last_ms or (time.perf_counter() - t1) * 1000
    print(f"[识别] {text!r}  ({infer_ms:.0f} ms, RTF {infer_ms / 1000 / (len(wav) / 16000):.3f})")
    check("识别出内容", bool(text and text.strip()), text)

    # 1) 稿件就是这句话 —— 应该一路对齐到句末
    s = Script.from_text(text, 14)
    a = Aligner(s)
    r = a.update(text)
    n = len(s.chars)
    print(f"[对齐] pos={r.pos}/{n - 1} conf={r.conf:.2f} delta={r.delta}")
    check("整句对齐到末尾", r.pos >= n - 3, f"{r.pos} vs {n - 1}")
    check("置信度高", r.conf > 0.8, r.conf)

    # 2) 稿件里这句话在第 3 句 —— 应该在长稿里定位到中间
    prefix = "大家好，我是老张。今天想跟你聊一个很多家长都问过我的问题。"
    s2 = Script.from_text(prefix + text + "我带过七届毕业班，见过太多这样的孩子。", 14)
    a2 = Aligner(s2)
    # 先对齐到第 2 句（模拟已经念到那儿）
    a2.reset(len(Script.from_text(prefix, 14).chars) - 6)
    r2 = a2.update(text)
    start_of_target = prefix
    idx = a2.script.text.find(text.rstrip("。"))
    print(f"[定位] pos={r2.pos} conf={r2.conf:.2f}  目标句起点={idx}")
    check("长稿里定位到目标句尾部", idx >= 0 and r2.pos >= idx, (r2.pos, idx))

    # 3) 耗时：对齐这一步本身要够快，不能拖累 5 Hz 的更新节奏
    ts = []
    for _ in range(100):
        t = time.perf_counter()
        a2.update(text)
        ts.append((time.perf_counter() - t) * 1000)
    med = statistics.median(ts)
    print(f"[耗时] 对齐中位 {med:.2f} ms")
    check("对齐 < 2 ms", med < 2.0, med)

    print(f"\n通过 {OK}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
