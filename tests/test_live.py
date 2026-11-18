"""实机联调：把音频灌进真正的 Listener 循环，看位置会不会被推着走。

不需要麦克风 —— 用一个假的 Recorder 顶替，其余（滑窗节拍、ASR、对齐器、
会话状态机、广播）全是生产代码。这是"念稿能不能自动跟"最接近真人的验证。

    python tests/test_live.py

会加载模型（首次十几秒）。
"""
import asyncio
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from app import config, model_finder
from app.audio import Recorder
from app.listener import Listener
from app.session import Session

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
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


class FakeRecorder(Recorder):
    """顶替真麦克风：tail() 永远返回"最近这段音频"，并把电平伪装成有人在说话。"""

    def __init__(self, wav: np.ndarray):
        super().__init__()
        self._wav = wav
        self.level = 0.06

    @property
    def running(self) -> bool:
        return True

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def tail(self, sec: float) -> np.ndarray:
        n = int(self.sr * sec)
        out = np.zeros(n, dtype=np.float32)
        take = min(n, len(self._wav))
        if take:
            out[-take:] = self._wav[-take:]
        return out


async def main() -> int:
    fx = ROOT / "tests" / "fixtures" / "asr_zh.wav"
    found, _ = model_finder.find()
    if not fx.exists() or found is None:
        print("[跳过] 缺样例音频或模型")
        return 0

    wav = load_wav(fx)
    heard = "甚至出现交易几乎停滞的情况。"      # 样例音频说的是这句

    # 稿件 = 这句话 + 后文。位置应当停在第一句末尾（约第 13 字），不会自己往后跑
    text = heard + "今天我想跟你聊一个很多家长都问过我的问题。"
    session = Session(dict(config.DEFAULT_UI), text)
    # 切到 AI 跟随（等价于控制台上把开关拨到右边）。
    # 留在 auto 的话，模型加载那十几秒里稿子会按 cps 自己滚到结尾。
    session.ui["follow_mode"] = "ai"
    session.start()

    msgs = []

    async def bc(m):
        msgs.append(m)

    lst = Listener(bc)
    lst.rec = FakeRecorder(wav)

    async def on_text(t):
        m = session.feed_asr(t)
        if m:
            await bc(m)

    lst.on_text = on_text

    # 生产环境里 server.py 有个 60 Hz 的心跳在推 Motion；测试里也得跑，
    # 否则只验证了对齐器，没验证「屏幕上真的动了」
    ticker_stop = False

    async def ticker():
        last = time.perf_counter()
        while not ticker_stop:
            await asyncio.sleep(1 / 60)
            now = time.perf_counter()
            session.tick(now - last)
            last = now

    tick_task = asyncio.create_task(ticker())

    print("[启动] 加载模型 + 开麦（假麦克风）…")
    t0 = time.perf_counter()
    await lst.start()
    open_sec = time.perf_counter() - t0
    print(f"[启动] {open_sec:.1f} s，引擎 {lst.engine.status()['device']} / {lst.engine.status()['dtype']}")
    check("开启成功", lst.on and lst.engine.ready, lst.error)

    if not lst.engine.ready:
        await lst.stop()
        print(f"\n通过 {OK}，失败 {FAIL}")
        return 1

    await asyncio.sleep(4.5)      # 让循环跑十几拍
    runs = lst.stats["runs"]
    await lst.stop()
    ticker_stop = True
    tick_task.cancel()

    print(f"[统计] 识别 {runs} 拍 / 4.5 s ≈ {runs / 4.5:.1f} Hz，"
          f"单次 {lst.stats['ms']} ms，RTF {lst.stats['rtf']}")
    check("循环在跑（至少 4 拍）", runs >= 4, runs)
    check("更新频率 ≥ 1.5 Hz", runs / 4.5 >= 1.5, runs / 4.5)
    check("推理快于实时", (lst.stats["rtf"] or 1) < 1.0, lst.stats["rtf"])

    pos_msgs = [m for m in msgs if m.get("type") == "pos"]
    snap = session.snapshot()
    shown = session._pos_int()          # 显示位置（字索引，已经过 Motion 平滑）
    print(f"[位置] 收到 {len(pos_msgs)} 条 pos 消息，"
          f"最终 line={snap['line']} readIdx={snap['readIdx']} → 第 {shown} 字")
    check("识别结果驱动了位置（AI 已接上）", session.aligned is True)
    check("对齐器停在第一句末尾附近", 10 <= session.aligner.pos <= 16,
          f"pos={session.aligner.pos} 期望≈13")
    check("显示位置跟上了对齐器（Motion 生效）", shown >= 10, f"第 {shown} 字")
    check("最后一拍置信度高", pos_msgs and pos_msgs[-1]["align"]["conf"] > 0.8,
          pos_msgs[-1] if pos_msgs else None)
    check("没有越过第二句", session.aligner.pos < 20, session.aligner.pos)

    print(f"\n通过 {OK}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
