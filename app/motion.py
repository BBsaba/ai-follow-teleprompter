"""位置平滑：把跳变的字位置磨平，避免行边界来回抽搐。

逐行模式下不使用前瞻（见文档 §4.3）——行是离散单位，提前半行会让
下一行提前变成"当前行"，而用户还在念上一行。
"""
from __future__ import annotations

import math


class Motion:
    def __init__(self, tau_fwd: float = 0.09, tau_back: float = 0.22):
        self.tau_fwd = tau_fwd
        self.tau_back = tau_back
        self.d = 0.0
        self.v = 0.0
        self.prev: float | None = None

    def snap(self, pos: float) -> None:
        self.d = float(pos)
        self.prev = float(pos)
        self.v = 0.0

    def step(self, pos: float, dt: float) -> float:
        if self.prev is None or dt <= 0:
            self.snap(pos)
            return self.d

        inst = (pos - self.prev) / dt
        inst = max(-40.0, min(40.0, inst))
        self.v = 0.8 * self.v + 0.2 * inst
        self.prev = pos

        tau = self.tau_back if pos < self.d else self.tau_fwd
        alpha = 1.0 - math.exp(-dt / max(tau, 1e-3))
        self.d += (pos - self.d) * alpha
        if abs(pos - self.d) < 0.02:
            self.d = float(pos)
        return self.d
