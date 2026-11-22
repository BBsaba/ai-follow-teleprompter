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

import bisect
from dataclasses import dataclass

from . import config
from .script import Script, char_tokens

# 范围判决用的三个数（见 Aligner.update）
#
#   GOOD_CONF  —— 近窗（±跟随范围）到这个置信度，就当「人就在附近」，不再出去侦察。
#                 正常跟读的匹配几乎都是 0.9~1.0；位置对不上时会掉到 0.5 上下，
#                 0.62 正好落在这两堆数之间。
#   SPY_MARGIN —— 外面要「比近窗好这么多」才算「明显更像」，否则宁可不动。
#   SPY_FACTOR —— 侦察半径 = 跟随范围 × 这个倍数。只用来判断「人是不是在范围外」，
#                 判断完就丢，**绝不拿它去落点**。
GOOD_CONF = 0.62
SPY_MARGIN = 0.10
SPY_FACTOR = 3
# 侦察半径的下限（字）。范围调得很小时（比如 2 行），3 倍只有 84 字，
# 连「撞车」都不一定够得着 —— 那样用户看到的就是「不跟、也不说为什么」。
# 400 字在 14~20 字/行下是 20~28 行，覆盖现实里的跳读距离。
SPY_MIN = 400

# 跟随半径的下限。
#
# ⛔ 为什么必须有（实测，2026-11-21）：窗口要装得下**当前这句话**。识别结果
#    一段话是 20~40 字，半径比它小的时候，DTW 只能把这句话的尾巴硬挤在窗口
#    边缘、逐字走 gap_asr（每个 0.85），置信度直接崩到 0.3 以下。
#    每行 20 字、范围 1 行（半径 20 字）实测：喂 900 字只跟到 20 字，**彻底停摆**，
#    而且因为「一个字都没动」，界面连「超出范围」都报不出来 —— 用户看到的就是
#    「跟读坏了」，不是「范围太小」。
#
#    半径 40 字 ≈ 一段 4 秒的话；3 行是为了让用户加一行真的能看到变化
#    （比 3 行还小时三者取最大，等于没区别）。
MIN_RADIUS = 40
MIN_LINES = 3

# 平局先验：稿件里同一句话出现两次时，两处代价完全相等，选谁全看插入顺序。
# 给「离当前位置远」的候选每个 token 加这么一点代价，让近的那个赢。
# ⚠️ 必须远小于一次替换代价（0.35），否则它会盖过真实的匹配差异。
NEAR_BIAS = 0.001

# 窗口截断的判定（见 _match）。两个条件同时成立才算：
#   ① 路径终点顶在窗口最后一格（`end == len(P)`）
#   ② 路径上一共跳过了 ≥ CLIP_MIN 个识别字
#
# ⛔ 为什么必须有（2026-11-21 实测）：窗口只有 ±N 字，识别结果比窗口长时，
#    DTW 会把装不下的部分逐字跳过（gap_asr 每个 0.85）。因为稿件窗口里有的是
#    同音、近音字，那些字并不是整齐地丢在结尾，而是**散在路径中间**被"捡"回去
#    匹配掉，剩下的才跳过。于是：代价不高、置信度还有 0.6~0.9，看着像一次成功
#    匹配，落点却在**窗口边缘**，而人其实在窗外几十字的地方。
#    更要命的是窗口边缘跟着 `pos` 一起走：这一拍贴到边缘，下一拍真正的目标就
#    落进窗口了。两拍走完一次本该被挡住的大跳，用户看到的还是"跟过去了"。
#    实测（范围 3 行 = 42 字）：片段跨度一到 +50，位移就被接受成 +42，然后再 +42。
#
# ⛔ 为什么不能只数「跳过了几个字」（第一版就是这么写的，失败）：正常跟读碰上
#    噪声（ASR 多听两三个字）也会跳到 5~6 个，而跨窗片段最小也是 6 —— 两堆数
#    在 6 上正面撞车，绝对阈值怎么定都有错。（实测 1200 条带噪声的正常跟读：
#    阈值 3 误挡 29%、阈值 5 误挡 1.4%、阈值 6 仍误挡 0.3%。）
#
#    真正干净的特征是**路径终点被顶在窗口最后一格**：人念的下一句已经在窗外，
#    DTW 无处可去，只能贴边收尾。而正常跟读即使噪声大到跳 6 个字，落点仍在
#    真实位置、离窗口末尾还有十几格。实测（600 条带噪声正常跟读 + 2352 条跨窗
#    片段）：`end == len(P) and skips >= 2` 的误挡 0 条、漏网 0 条。
#
# CLIP_MIN 取 2 而不是 1：给「人正好站在范围边界上」留 1 个字的余量。
CLIP_MIN = 2


@dataclass
class AlignResult:
    pos: int          # 对齐后的字索引（念到第几个字）
    conf: float       # 0–1，低于 min_conf 时 pos 原样返回
    delta: int        # 相对上一位置移动了多少字
    score: float = 0.0
    over: int = 0     # 因「超出跟随范围」没跟时，那个位置离当前位置多少字


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
    anchor: int | None = None,
    bias: float = 0.0,
) -> tuple[float, int, int]:
    """返回 (最小代价, 终点在 P 中的下标+1, 跳过的识别字数)。

    P 是稿件窗口的 token，q 是识别结果的 token。
    q 必须整体走完（插入/删除只发生在 P 一侧的自由端与内部空格）。

    `anchor` / `bias` 是平局裁决：稿件里同一句话出现两次时，两处代价完全相等，
    光看代价分不出该选哪个 —— 于是给「离 anchor 远」的候选加一点点代价
    （`bias` 每个 token），让**近的那个赢**。bias 必须远小于一次替换代价
    （0.35），否则它会盖过真实的匹配差异，变成「近的就是对的」。
    返回的 score 是**不含** bias 的原始代价，置信度不能被它污染。

    ⛔ 第三个返回值（`skips`）是给「窗口截断」用的：最优路径上一共有多少个
    识别字是**跳过**的（gap_asr），也就是「人念了、但稿子窗口里找不到位置」。

    为什么必须数它：窗口装不下整句话时，DTW 会把装不下的部分逐字跳过 ——
    代价只有 0.85/字，而且**不是整齐地丢在结尾**，是散在路径中间的。于是
    代价算出来不高、置信度还有 0.6~0.9，看着像一次成功匹配，落点却在窗口
    边缘附近，而人其实在窗外几十字的地方。调用方（`_match`）据此拒绝。
    """
    m, n = len(P), len(q)
    if m == 0 or n == 0:
        return 0.0, 0, 0

    INF = float("inf")

    # j = 0：q 一个都没消费，起点在 P 的任意位置都免费（起点自由）
    prev = [0.0] * (m + 1)
    prev_skip = [0] * (m + 1)

    for j in range(1, n + 1):
        qj = q[j - 1]
        cur = [INF] * (m + 1)
        cur_skip = [0] * (m + 1)
        for i in range(1, m + 1):
            best = prev[i - 1] + token_cost(P[i - 1], qj, near)   # 匹配/替换
            skip = prev_skip[i - 1]
            v = prev[i] + gap_asr          # 跳过识别侧一个 token（ASR 多听了一个字）
            if v < best:
                best, skip = v, prev_skip[i] + 1
            v = cur[i - 1] + gap_script    # 跳过稿件侧一个字（ASR 漏了一个字）
            if v < best:
                best, skip = v, cur_skip[i - 1]
            cur[i] = best
            cur_skip[i] = skip
        prev, prev_skip = cur, cur_skip

    # 终点自由：最后一列（q 全部消费完）里取代价最小的格子
    best_val = INF
    best_score = 0.0
    best_end = 0
    best_skip = 0
    for i in range(1, m + 1):
        val = prev[i]
        if anchor is not None and bias:
            val += bias * abs(i - anchor)
        if val < best_val:
            best_val, best_score, best_end, best_skip = val, prev[i], i, prev_skip[i]
    return best_score, best_end, best_skip


class Aligner:
    """跟着 ASR 文本推进稿件位置 —— 只认「附近的稿子」，太远的一律不跟。

    整台机器只有一句话：**每次都在「当前位置前后各 N 行」以内找，找到就挪过去，
    找不到就不动。** 那个 N 就是界面上的「跟随范围」，用户自己调。

    为什么是「范围」而不是「速度」（v2.3.x 三次返工的最终结论）：
        用户要解决的是「某个词和十几行以后的内容撞车，屏幕忽然跳一大段」。
        这本质上是「该不该去那么远」的问题，不是「去得多快」的问题。
        按速度限，它照样会去，只是慢——用户看到画面缓缓滑过去，仍然觉得没管住；
        按范围限，窗外的匹配**根本进不了候选**，一步都不用走。
        而范围本来就在搜索窗口里，收窄窗口就是收窄范围，不需要任何额外的闸。

    一拍的处理顺序：
        ① 在 ±N 行里找（近窗）
        ② 近窗不干净（conf < GOOD_CONF）→ 出去侦察一圈（±3N 行）
           侦察到「外面明显更像」→ 认定人已经走到范围外了 → **这拍不跟**，
           而且近窗那个凑出来的假匹配也不许把位置拖走
        ③ 近窗够干净 → 直接采纳
    """

    def __init__(self, script: Script, cfg: dict | None = None):
        c = cfg or config.ALIGN
        self.script = script
        # 没设跟随范围（0）时的固定窗口，保留给单测与「还没接上 UI」的裸用法
        self.lookback = int(c["lookback"])
        self.lookahead = int(c["lookahead"])
        self.min_conf = float(c["min_conf"])
        self.back_step_max = int(c["back_step_max"])
        self.back_conf = float(c["back_conf"])
        self.gap_script = float(c["gap_script"])
        self.gap_asr = float(c["gap_asr"])
        self.near = float(c["cost_near"])

        # 跟随范围，单位「行」，0 = 用上面那对固定窗口。
        #
        # 默认 0 而不是取 DEFAULT_UI 里的数：Aligner 是底层组件，不该假设
        # 「UI 一定有这个键」。真实运行由 Session._apply_align_limits() 每拍写入。
        self.follow_lines = 0

        self.pos = 0
        # 上一拍「因为超出范围而没跟」时，那个更像的位置离当前位置多少字（带符号）。
        # 给控制台显示「超出范围 · 差 N 行」用 —— 不显示的话，用户只会看到
        # 屏幕忽然不动了，然后开始怀疑是程序坏了。
        self.over = 0

        self.last = AlignResult(0, 0.0, 0)
        self.updates = 0        # 成交次数（调试用）
        self.rejects = 0        # 被置信度 / 范围挡掉的次数

    # ---------- 生命周期 ----------
    def reset(self, pos: int = 0) -> None:
        self.pos = max(0, int(pos))
        self.over = 0
        self.last = AlignResult(self.pos, 0.0, 0)

    # ---------- 范围 ----------
    def radius(self) -> int:
        """跟随半径（字）：前后各多少字以内算「附近」。

        三选一取最大 —— 用户设的、至少 3 行、至少 40 字。后两条见文件头
        MIN_RADIUS / MIN_LINES 的说明：它们不是保守，是**不然跟读会停摆**。
        """
        per = int(self.script.per_line) or 1
        return max(int(self.follow_lines) * per, MIN_LINES * per, MIN_RADIUS)

    def window(self) -> tuple[int, int]:
        """(往后看多少字, 往前看多少字)。"""
        if self.follow_lines > 0:
            r = self.radius()
            return r, r
        return self.lookback, self.lookahead

    # ---------- 对齐 ----------
    def update(self, asr_text: str) -> AlignResult:
        q = char_tokens(asr_text)
        # 一两个字的信息量太小，DTW 会随便找个同音字糊上去
        if len(q) < 2:
            return self.last

        n_chars = len(self.script.chars)
        if n_chars == 0:
            return self.last

        back, ahead = self.window()
        near = self._match(q, self.pos - back, self.pos + ahead)
        self.over = 0

        # ② 近处不干净，才出去看一眼 —— 平时（正常跟读）压根不走这条
        if near is None or near[0] < GOOD_CONF:
            spy = max(ahead * SPY_FACTOR, SPY_MIN)
            far = self._match(q, self.pos - spy, self.pos + spy)
            if far and far[0] >= (near[0] if near else 0.0) + SPY_MARGIN:
                # 范围外有个「明显更像」的地方 → 人已经在范围外了。
                # 这拍不跟，也不让近处那个凑出来的假匹配把位置拖到窗口边缘。
                self.over = far[1] - self.pos
                self.rejects += 1
                self.last = AlignResult(self.pos, far[0], 0, far[2], self.over)
                return self.last

        conf = near[0] if near else 0.0
        if not near or conf < self.min_conf:
            self.rejects += 1
            self.last = AlignResult(self.pos, conf, 0, near[2] if near else 0.0)
            return self.last

        new_pos = near[1]

        # 跳过紧随其后的标点。不跳的话，用户正好在逗号处停下来时，
        # 前面全灰了这个逗号还是白的——因为「念完」是按字索引算的。
        while new_pos < n_chars and self.script.chars[new_pos].is_punct:
            new_pos += 1
        new_pos = min(new_pos, n_chars - 1)

        # 迟滞：置信度不够高时不许大幅回退，否则念错一个字整行往回弹
        if new_pos < self.pos - self.back_step_max and conf < self.back_conf:
            new_pos = self.pos

        delta = new_pos - self.pos
        self.pos = new_pos
        self.updates += 1
        self.last = AlignResult(new_pos, conf, delta, near[2])
        return self.last

    # ---------- 搜索 ----------
    def _match(self, q, lo: int, hi: int):
        """在 [lo, hi) 这段稿子里找 q，返回 (conf, 下一个字的位置, score) 或 None。"""
        n = len(self.script.chars)
        lo = max(0, min(int(lo), n))
        hi = max(lo, min(int(hi), n))
        if hi <= lo:
            return None
        P, idxs = self.script.token_window(lo, hi)
        if not P:
            return None
        # 平局时偏向「离当前位置近」的那个副本：稿件里同一句话出现两次时，
        # 两处代价一模一样，没有这个先验就只能听插入顺序的，可能选到远处那份。
        anchor = bisect.bisect_left(idxs, self.pos)
        score, end, skips = semiglobal_dtw(
            P, q, self.gap_script, self.gap_asr, self.near,
            anchor=anchor, bias=NEAR_BIAS,
        )
        if end <= 0:
            return None
        # 终点顶在窗口最后一格 = 这句话的尾巴已经在窗外，落点只是"窗口边缘"，
        # 人的真实位置在更远的地方。当作没找到（conf=0），让 update() 去开侦察
        # 窗、报「超出范围」，而不是先把屏幕贴到边缘、下一拍再走完剩下的距离。
        #
        # `hi >= n` 时不算：那不是范围边界，是稿子到头了 —— 人在最后一句上念，
        # 落点本来就该贴到最后一个字。
        if end >= len(P) and skips >= CLIP_MIN and hi < n:
            return 0.0, idxs[end - 1] + 1, score
        conf = max(0.0, min(1.0, 1.0 - score / (len(q) * 1.0)))
        return conf, idxs[end - 1] + 1, score
