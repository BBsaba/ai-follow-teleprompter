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

import time
from dataclasses import dataclass

from . import config
from .script import Script, char_tokens

# 远窗判决门槛（见 Aligner._locate）
#   JUMP_EASY   —— 近窗匹配到这个置信度以上，就当「人就在附近」，不再搜远处
#   JUMP_CONF   —— 远窗必须达到这个置信度，才有资格当「跳读候选」
#   JUMP_MARGIN —— 而且要比近窗好这么多，才算「明显更好」
#
# 0.60 不是一个拍脑袋的数：正常跟读的匹配几乎都是 0.9~1.0，掉到 0.6 以下一定
# 是位置对不上（念串行、跳读、或者 ASR 崩了）。0.70 是「候选」的底线，配合
# 「连中两拍」一起用，把单拍的假匹配挡在外面（探针实测假匹配能到 0.48）。
JUMP_EASY = 0.60
JUMP_CONF = 0.70
JUMP_MARGIN = 0.15


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
    """跟着 ASR 文本推进稿件位置。

    每次 update 都拿「刚听到的这一小段」重新在稿子上找一遍，不累积概率；
    但保留三个跨拍状态，各有各的用处，别混：

    | 状态 | 干什么用 |
    |---|---|
    | `raw` | 对齐器认为用户念到哪 —— **下一拍搜索窗口锚它** |
    | `pos` | 屏幕显示到哪 —— 按 max_jump_lines 追 `raw` |
    | `_cand` | 远处的候选落点，连中两拍才认（挡单拍假匹配） |
    """

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

        # 推进速度上限，单位「行/秒」，0 = 不限。
        #
        # 默认 0（不限）而不是取 DEFAULT_UI 里的 5：Aligner 是底层组件，不该假设
        # 「UI 一定有这个键、且默认是 5」。真实运行由 Session._apply_align_limits()
        # 每拍显式写进来；测试里直接 new 出来测对齐精度时，不该被限速干扰
        # ——（v2.3.0 返工时踩到：默认 5 让整套基础对齐用例全红，因为测试连续调用
        #   没有时间间隔，dt≈0 → 每拍只走 1 字）
        self.max_jump_lines = 0

        # 限速状态：上一拍的时间戳（None = 还没收到过第一拍）+ 没用完的额度
        # ⚠️ 用 None 而不是 0.0 当「没初始化」：0.0 是合法时间戳，测试里 now=0.0
        #    很常见，混用会让第一拍重复发一次额度。
        self._last_t: float | None = None
        self._budget = 0.0
        # 待确认的「远处候选」位置（见 _locate）
        self._cand = None

        # ★ 两个位置，别搞混（v2.3.0 第三次返工的关键）
        #   raw —— 对齐器认为「用户真的念到哪了」，不受限速影响
        #   pos —— 屏幕上显示到哪了，按 max_jump_lines 慢慢往 raw 追
        # 分开之前只有一个 pos，既是显示位置又是搜索窗口的锚点：
        # 限速把它夹住 → 窗口跟着往回缩 → 下一拍根本搜不到用户在哪 → 越夹越找不到。
        # 探针实测：窗口前沿之外 100 字整段失效，还冒出 conf=0.48 的假匹配。
        self.raw = 0
        self.pos = 0
        self.last = AlignResult(0, 0.0, 0)
        self.updates = 0        # 成交次数（调试用）
        self.rejects = 0        # 被置信度挡掉的次数

    # ---------- 生命周期 ----------
    def reset(self, pos: int = 0) -> None:
        self.pos = max(0, int(pos))
        self.raw = self.pos
        self._last_t = None
        self._budget = 0.0
        self._cand = None
        self.last = AlignResult(self.pos, 0.0, 0)

    # ---------- 对齐 ----------
    def update(self, asr_text: str, now: float | None = None) -> AlignResult:
        q = char_tokens(asr_text)
        # 一两个字的信息量太小，DTW 会随便找个同音字糊上去
        if len(q) < 2:
            return self.last

        n_chars = len(self.script.chars)
        if n_chars == 0:
            return self.last

        found = self._locate(q)
        conf = found[0] if found else 0.0

        if not found or conf < self.min_conf:
            self.rejects += 1
            self.last = AlignResult(self.pos, conf, 0, found[2] if found else 0.0)
            return self.last

        # found[1] 是「已念完的最后一个 token」的下标+1 → 下一个要念的字
        new_raw = found[1]

        # 跳过紧随其后的标点。不跳的话，用户正好在逗号处停下来时，
        # 前面全灰了这个逗号还是白的——因为「念完」是按字索引算的。
        while new_raw < n_chars and self.script.chars[new_raw].is_punct:
            new_raw += 1
        new_raw = min(new_raw, n_chars - 1)

        # 回退迟滞：置信度不够高时不许大幅回退，否则念错一个字整行往回弹。
        # （对着 raw 比，不是 pos —— pos 可能正落在后面追着呢）
        if new_raw < self.raw - self.back_step_max and conf < self.back_conf:
            new_raw = self.raw

        self.raw = new_raw

        # 收敛：限制「显示位置推进的速度」，不是「单拍步长」（0 = 不限）。
        #
        # 夹在这里而不是 Session.feed_asr() 里，是因为 pos 还要算 delta、写进
        # AlignResult 给前端用；在外面夹会让「返回的 pos」和「内部记的 pos」脱节。
        #
        # 滚轮完全不受影响 —— wheel() 走的是 reset()，人工接管时 raw 和 pos 一起挪过去。
        if self.max_jump_lines > 0:
            new_pos = self._rate_limit(new_raw, now)
        else:
            new_pos = new_raw
            self._budget = 0.0        # 不限速时不留额度，免得下次开启时突然冲一下

        delta = new_pos - self.pos
        self.pos = new_pos
        self.updates += 1
        self.last = AlignResult(new_pos, conf, delta, found[2])
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
        score, end = semiglobal_dtw(P, q, self.gap_script, self.gap_asr, self.near)
        if end <= 0:
            return None
        conf = max(0.0, min(1.0, 1.0 - score / (len(q) * 1.0)))
        return conf, idxs[end - 1] + 1, score

    def _locate(self, q):
        """找 q 在稿子上的位置：先近后远，远了还要再确认一拍。

        为什么必须分两级（v2.3.0 实测）：
            单窗搜索的前沿是 raw + lookahead。用户一把跳过 5 行以上，
            人就已经站在窗口外面了 —— 怎么算都匹配不上，屏幕直接冻住。
            用户看到的就是「跳到第 7 行还跟，跳到第 8 行就不跟了」，
            而第 7/8 行的那条分界线，其实只是 lookahead/每行字数 算出来的巧合。
        """
        near = self._match(q, self.raw - self.lookback, self.raw + self.lookahead)
        if near and near[0] >= JUMP_EASY:
            # 近处就吻合得很好 —— 正常跟读走这条，和加限速之前一模一样
            self._cand = None
            return near

        # 近处对不上，才放开半径去找（多算一次 DTW，只在异常拍才发生）
        far = self._match(q, self.raw - self.wide_back, self.raw + self.wide_ahead)
        if far and far[0] >= JUMP_CONF and far[0] >= (near[0] if near else 0.0) + JUMP_MARGIN:
            # 远处找到「明显更好」的匹配 —— 但先别信，下拍再看是不是还指着那儿。
            # 单拍的假匹配（同音字凑巧连成一句）很常见，连中两拍才是真跳读。
            if self._cand is not None and abs(far[1] - self._cand) <= self.script.per_line:
                self._cand = None
                return far
            self._cand = far[1]
            return None                   # 有强候选，但还没确认 → 这拍原地不动
        return near

    # 远窗的半径。按「行」算而不是按「字」算 —— 用户设的每行字数会变，
    # 写死成字就等于「每行字数一变，可跳的行数就跟着变」（那个 7/8 行的分界线
    # 就是这么来的：100 字 ÷ 20 字/行 = 5 行）。
    @property
    def wide_back(self) -> int:
        return max(self.lookback, int(self.script.per_line) * 12)

    @property
    def wide_ahead(self) -> int:
        return max(self.lookahead, int(self.script.per_line) * 20)

    def _rate_limit(self, target: int, now: float | None) -> int:
        """把显示位置压回「每秒最多 max_jump_lines 行」的速度里。

        为什么按**时间**算、而不是按**拍**算（v2.3.0 第一次返工）：
            ASR 是 3 Hz 一小段一小段送进来的。用户读快时，跨 5 行（100 字）是
            **分 5~6 拍**送到的，每拍只有十几字 —— 按拍限幅的话每拍都不到阈值，
            夹子**一次都不会触发**，用户体感就是「限位完全没效果」。
            「一拍（0.33 秒）」用户根本感知不到，能感知的最小单位是「一秒」。

        这里只有一件事：按 dt 发额度，用完就停。没有迟滞、没有加速。

        ⛔ 曾经有过 boost = min(1 + starve*0.5, 3.0)，理由是「怕真跳读的人永久落后」。
           实测代价是毁灭性的：设 2 行/秒（40 字/秒）时实际跑出 120 字/秒，
           跳 5 行本该走 2.5 秒，实际 1.65 秒 —— 用户体感「唰地跟过去，限位没生效」。
           **滑块的值必须等于真实速度**，不然「设置」和「体验」永远对不上。

        ⛔ 也曾经有过「单拍超限就先冻 3 拍」的迟滞，想用它分辨误锁。
           实测两个毛病：① 用户先看到一秒的「卡死」，再看到画面滑动，更不像限位；
           ② 它把误锁的判定和限速混在一起，参数互相牵制，调一个坏一个。
           现在误锁在**检测层**就挡掉了（见 _locate 的连中两拍才算数），
           限速器只管限速，职责单一。

        额度带小数累计（_budget）：dt=0.33、上限 40 字/秒 时每拍 13.2 字，
        直接 int() 会一律截成 13，实际速度只有 39 字/秒 —— 一点点，但没理由欠着。
        """
        t = now if now is not None else time.monotonic()
        if self._last_t is None:
            dt = 0.33                     # 首拍按 3 Hz 估，别给一个巨大的初始额度
        else:
            dt = max(0.0, min(1.0, t - self._last_t))
        self._last_t = t

        need = target - self.pos
        if need == 0:
            self._budget = 0.0
            return target

        limit = self.max_jump_lines * int(self.script.per_line)   # 字/秒
        quota = limit * dt + self._budget
        if abs(need) <= quota:
            self._budget = 0.0            # 没被限住，额度清零，不留到下一拍
            return target

        step = int(quota)
        if step <= 0:
            self._budget = quota          # 额度还不够走一个字，先存在这儿
            return self.pos

        self._budget = quota - step
        return self.pos + (1 if need > 0 else -1) * step
