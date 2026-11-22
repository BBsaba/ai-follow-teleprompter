"""会话状态机 + 位置驱动。

IDLE ── start ──▶ RUNNING ⇄ PAUSED
  ▲                  │
  └────── stop ──────┘

位置有两个来源，**由用户显式二选一**（`ui["follow_mode"]`）：

  · auto —— 按 cps 匀速自动滚动，不需要麦克风（练手 / 已知语速的稿子）；
  · ai   —— 只在识别结果对齐上稿子时才动，**不说话就不动**。

设计上刻意只留一个模式字段：早先版本用「sim_enabled + asr_drive + 麦克风开关」
三个布尔量表达同一件事，结果是三处不同步、还会互相打架（开麦加载模型的那十几秒里
模拟推进把稿子滚到了结尾）。现在模式只存在 `ui` 里，改动立刻生效、重启后还记得。
"""
from __future__ import annotations

from . import config
from .align import Aligner
from .motion import Motion
from .script import Script


class Session:
    def __init__(self, ui: dict, text: str = ""):
        self.ui = ui                      # 与 state["ui"] 同一个对象，改它就是改配置
        self.raw_text = text
        self.script = Script.from_text(text, int(ui["per_line"]))
        self.motion = Motion(config.MOTION["tau_fwd"], config.MOTION["tau_back"])
        self.aligner = Aligner(self.script)
        self._apply_align_limits()
        self.state = "IDLE"
        self.pos = 0.0
        self.aligned = False              # 本次录制里 AI 是否已经接上（纯显示用）
        self.align_info: dict = {}
        self._last_key = None

    # ---------- 推进方式 ----------
    @property
    def mode(self) -> str:
        return "ai" if self.ui.get("follow_mode") == "ai" else "auto"

    def on_mode_changed(self) -> None:
        """切换推进方式时的收尾。

        切到 ai 时把对齐器锚点对到当前位置：auto 模式期间位置是 cps 推的，
        对齐器还停在上次它自己认为的地方，不重锚第一拍就会把画面拽回去。
        """
        if self.mode == "ai":
            self.aligner.reset(int(self.pos))

    # ---------- 稿件 ----------
    def _apply_align_limits(self) -> None:
        """把「跟随范围」从 ui 同步给对齐器。

        这个数字进的是对齐器的搜索窗口（`Aligner.window()`），所以它改的是
        「允许跟多远」，不是「允许跟多快」—— 见 align.py 顶部那段说明。

        为什么每拍都同步，而不是改设置时同步一次：`self.ui` 就是 `state["ui"]`
        本身，谁都能直接往里写（控制台滑块、设置页、以后的别的接口）。每拍读一次
        dict 是最省事的一致做法 —— 反正只是一次取值，量级可以忽略。

        用 `ui.get(键, 默认值)` 而不是 `ui[键]`：老 `state.json` 里没有这个键，
        `store.load_state()` 虽然会用 `dict(DEFAULT_UI)` 补上，但万一哪天有人绕过
        它直接构造 ui，`ui[键]` 就是一个 KeyError，直接把跟读打挂。
        """
        self.aligner.follow_lines = int(
            self.ui.get("follow_lines", config.DEFAULT_UI["follow_lines"])
        )

    def rebuild(self, text: str | None = None) -> None:
        if text is not None:
            self.raw_text = text
        self.script = Script.from_text(self.raw_text, int(self.ui["per_line"]))
        self.aligner = Aligner(self.script)
        self._apply_align_limits()          # 新建的 Aligner 会回到默认值，得重新同步
        self.pos = 0.0
        self.motion.snap(0.0)
        self.state = "IDLE"
        self.aligned = False
        self.align_info = {}
        self._last_key = None

    # ---------- 控制 ----------
    def start(self) -> None:
        self.pos = 0.0
        self.motion.snap(0.0)
        self.aligner.reset(0)
        self.aligned = False
        self.state = "RUNNING"

    def toggle_pause(self) -> None:
        if self.state == "RUNNING":
            self.state = "PAUSED"
        elif self.state == "PAUSED":
            self.state = "RUNNING"

    def stop(self) -> None:
        self.state = "IDLE"
        self.pos = 0.0
        self.motion.snap(0.0)
        self.aligner.reset(0)
        self.aligned = False
        self.align_info = {}

    def wheel(self, delta: int) -> None:
        """delta=+1 下一行，-1 上一行。"""
        if self.state == "IDLE" or not self.script.lines:
            return
        cur = self.script.line_of(self.pos)
        new = max(0, min(len(self.script.lines) - 1, cur + delta))
        self.pos = float(self.script.line_start(new))
        self.motion.snap(self.pos)
        # 滚轮是"人接管"，对齐器锚点必须一起挪，否则下一拍 ASR 立刻把位置拉回去
        self.aligner.reset(int(self.pos))

    # ---------- 识别驱动 ----------
    def feed_asr(self, text: str) -> dict | None:
        """吃一段 ASR 文本；有把握就把位置挪过去，并返回要广播的消息。

        auto 模式下直接丢弃：用户既然选了自动滚动，就不该被嘴影响。
        """
        if self.state != "RUNNING" or not text or self.mode != "ai":
            return None
        self._apply_align_limits()
        res = self.aligner.update(text)
        # over = 这一拍「因为超出跟随范围而没跟」时，那个更像的位置离屏幕多少字。
        # 不报出来的话，用户只会看到屏幕忽然不动了，以为程序卡死 ——
        # 「静默地不跟」正是前几轮反复被投诉的那个体验。
        per = max(1, int(self.script.per_line))
        self.align_info = {"conf": round(res.conf, 3), "delta": res.delta,
                           "pos": res.pos, "score": round(res.score, 2),
                           "over": res.over,
                           "overLines": round(abs(res.over) / per, 1)}
        if res.conf < self.aligner.min_conf:
            return None
        self.aligned = True
        self.pos = float(res.pos)
        return {"type": "pos", "pos": self.snapshot(), "align": self.align_info}

    # ---------- 查询 ----------
    def _pos_int(self) -> int:
        if not self.script.chars:
            return 0
        return max(0, min(int(round(self.motion.d)), len(self.script.chars) - 1))

    def snapshot(self) -> dict:
        p = self._pos_int()
        line = self.script.line_of(p)
        read_idx = max(0, min(p - self.script.line_start(line), self.script.line_len(line)))
        return {"line": line, "readIdx": read_idx, "state": self.state}

    # ---------- 心跳 ----------
    def tick(self, dt: float) -> dict | None:
        n = len(self.script.chars)
        # 只有 auto 模式才自己走。ai 模式下没识别到就停在原地——
        # 这正是用户要的"不自己滚动"。
        if self.state == "RUNNING" and n and self.mode == "auto":
            self.pos = min(self.pos + float(self.ui["cps"]) * dt, float(n - 1))
            if self.pos >= n - 1:
                self.state = "IDLE"
        self.motion.step(self.pos, dt)

        snap = self.snapshot()
        key = (snap["line"], snap["readIdx"], snap["state"])
        if key == self._last_key:
            return None
        self._last_key = key
        return {"type": "pos", "pos": snap}
