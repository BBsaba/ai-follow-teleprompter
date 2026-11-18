"""受限对齐器：把「刚听到的一段话」映射成「稿子念到第几个字」。

思路来自规划 §4.2：稿子是**已知**的，所以这不是通用的语音识别问题，
而是「拿最近的 4 秒语音，去稿子上的一个窗口里找到它出现的位置」——
受限匹配，比通用 ASR 精确得多，也便宜得多（窗口 150 × 20 ≈ 3k 格，毫秒级）。

为什么必须走拼音而不是汉字：
    ASR 把「是」听成「事」、把「在」听成「再」，汉字层面就是 100% 错误；
    拼音层面它们声母相同（sh/z 不同、韵母 i 相同），代价只有 0.35，
    不足以触发跳位。这是中文提词器必须过的一道关。

两级代价（声母/韵母分开比）：
    完全相同            0
    同韵母不同声母       0.35    "字" vs "次"
    同声母不同韵母       0.35    "是" vs "事"
    完全不同            1.0

半全局 DTW（q 必须整体匹配，P 的两端可以自由空转）：
    · 起点自由 —— 你不知道这 4 秒是从稿子哪一句开始念的；
    · 终点自由 —— 取最后一列最小值的格子作为结束位置；
    · 中间允许跳过：稿件侧漏字（gap_script）比识别侧多字（gap_asr）更常见。

⛔ 一个必须记住的坑：`Script.pinyin_window()` 会过滤标点，返回的下标和
    `chars` 不再一一对应。所以这里一律用 `token_window()`，它把每个 token
    对应的**字索引**一起带出来，否则位置会偏出标点那么多个字。
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .script import Script, char_tokens


@dataclass
class AlignResult:
    pos: int          # 对齐后的字索引（念到第几个字）
    conf: float       # 0–1，低于 min_conf 时 pos 原样返回
    delta: int        # 相对上一位置移动了多少字
    score: float = 0.0


def token_cost(a: tuple[str, str], b: tuple[str, str], near: float = 0.35) -> float:
    """两个拼音 token 的替换代价。"""
    ai, af = a
    bi, bf = b
    if ai == bi and af == bf:
        return 0.0
    # 韵母相同、声母不同（字/次、是/事 的声母其实不同，这里覆盖的是 sh/s 同韵类）
    if af == bf and af:
        return near
    # 声母相同、韵母不同（an/ang 前后鼻音、en/eng）
    if ai == bi and ai:
        return near
    return 1.0


def semiglobal_dtw(
    P: list[tuple[str, str]],
    q: list[tuple[str, str]],
    gap_script: float = 0.55,
    gap_asr: float = 0.85,
    near: float = 0.35,
) -> tuple[float, int]:
    """返回 (最小代价, 终点在 P 中的下标+1)。

    P 是稿件窗口的 token，q 是识别结果的 token。
    q 必须整体走完（插入/删除只发生在 P 一侧的自由端与内部空格）。
    """
    m, n = len(P), len(q)
    if m == 0 or n == 0:
        return 0.0, 0

    INF = float("inf")

    # j = 0：q 一个都没消费，起点在 P 的任意位置都免费（起点自由）
    prev = [0.0] * (m + 1)

    for j in range(1, n + 1):
        qj = q[j - 1]
        cur = [INF] * (m + 1)
        for i in range(1, m + 1):
            best = prev[i - 1] + token_cost(P[i - 1], qj, near)   # 匹配/替换
            v = prev[i] + gap_asr          # 跳过识别侧一个 token（ASR 多听了一个字）
            if v < best:
                best = v
            v = cur[i - 1] + gap_script    # 跳过稿件侧一个字（ASR 漏了一个字）
            if v < best:
                best = v
            cur[i] = best
        prev = cur

    # 终点自由：最后一列（q 全部消费完）里取代价最小的格子
    best_score = INF
    best_end = 0
    for i in range(1, m + 1):
        if prev[i] < best_score:
            best_score, best_end = prev[i], i
    return best_score, best_end


class Aligner:
    """跟着 ASR 文本推进稿件位置。每次 update 都是独立对齐，不依赖历史。"""

    def __init__(self, script: Script, cfg: dict | None = None):
        c = cfg or config.ALIGN
        self.script = script
        self.lookback = int(c["lookback"])
        self.lookahead = int(c["lookahead"])
        self.min_conf = float(c["min_conf"])
        self.back_step_max = int(c["back_step_max"])
        self.back_conf = float(c["back_conf"])
        self.gap_script = float(c["gap_script"])
        self.gap_asr = float(c["gap_asr"])
        self.near = float(c["cost_near"])

        self.pos = 0
        self.last = AlignResult(0, 0.0, 0)
        self.updates = 0        # 成交次数（调试用）
        self.rejects = 0        # 被置信度挡掉的次数

    # ---------- 生命周期 ----------
    def reset(self, pos: int = 0) -> None:
        self.pos = max(0, int(pos))
        self.last = AlignResult(self.pos, 0.0, 0)

    # ---------- 对齐 ----------
    def update(self, asr_text: str) -> AlignResult:
        q = char_tokens(asr_text)
        # 一两个字的信息量太小，DTW 会随便找个同音字糊上去
        if len(q) < 2:
            return self.last

        n_chars = len(self.script.chars)
        if n_chars == 0:
            return self.last

        lo = max(0, self.pos - self.lookback)
        hi = min(n_chars, self.pos + self.lookahead)
        P, idxs = self.script.token_window(lo, hi)
        if not P:
            return self.last

        score, end = semiglobal_dtw(P, q, self.gap_script, self.gap_asr, self.near)
        conf = 1.0 - score / (len(q) * 1.0)
        conf = max(0.0, min(1.0, conf))

        if conf < self.min_conf or end <= 0:
            self.rejects += 1
            self.last = AlignResult(self.pos, conf, 0, score)
            return self.last

        # end 是「已念完的最后一个 token」的下标+1 → 下一个要念的字
        new_pos = idxs[end - 1] + 1

        # 跳过紧随其后的标点。不跳的话，用户正好在逗号处停下来时，
        # 前面全灰了这个逗号还是白的——因为「念完」是按字索引算的。
        n = n_chars
        while new_pos < n and self.script.chars[new_pos].is_punct:
            new_pos += 1
        new_pos = min(new_pos, n - 1)

        # 迟滞：置信度不够高时不许大幅回退，否则念错一个字整行往回弹
        if new_pos < self.pos - self.back_step_max and conf < self.back_conf:
            new_pos = self.pos

        delta = new_pos - self.pos
        self.pos = new_pos
        self.updates += 1
        self.last = AlignResult(new_pos, conf, delta, score)
        return self.last
