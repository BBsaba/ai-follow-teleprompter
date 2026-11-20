"""对齐器单测。`python tests/test_align.py`

覆盖规划里点名的五类情况：正确 / 漏字 / 多字 / 同音 / 跳句，
外加两条回归：标点不得让位置偏移、噪音不得乱跳。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.align import Aligner, semiglobal_dtw, token_cost
from app.script import Script, char_tokens

OK = 0
FAIL = 0

TEXT = (
    "大家好，我是老张。今天想跟你聊一个很多家长都问过我的问题："
    "孩子明明很努力，成绩却一直上不去，问题到底出在哪？"
    "我带过七届毕业班，见过太多这样的孩子。他们不是不聪明，"
    "也不是不肯下功夫，而是把力气用错了地方。"
)


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


def make():
    s = Script.from_text(TEXT, 14)
    return s, Aligner(s)


def chars_of(s, lo, hi):
    """取 [lo, hi) 的原文（含标点），用来模拟"用户念了这一段"。"""
    return "".join(c.ch for c in s.chars[lo:hi])


def expect_after(s, hi):
    """念到 hi 之前最后一个字之后，位置应该落在哪。

    跳过紧随其后的标点：用户停在逗号处时，逗号也该一起变灰。
    """
    idxs = [c.idx for c in s.chars[:hi] if not c.is_punct]
    if not idxs:
        return 0
    p = idxs[-1] + 1
    n = len(s.chars)
    while p < n and s.chars[p].is_punct:
        p += 1
    return min(p, n - 1)


def test_cost():
    print("[代价函数]")
    # 真·同音字：拼音完全一样，代价为 0 —— 这正是走拼音的意义
    a, b = char_tokens("是")[0], char_tokens("事")[0]
    check("同音字代价为 0（是/事）", token_cost(a, b) == 0.0, token_cost(a, b))
    check("拼音确实相同（是/事）", a == b, (a, b))
    c, d = char_tokens("字")[0], char_tokens("次")[0]
    check("同韵母不同声母给 0.35（字/次）", abs(token_cost(c, d) - 0.35) < 1e-9, token_cost(c, d))
    e, f = char_tokens("三")[0], char_tokens("桑")[0]
    check("前后鼻音给 0.35（三/桑）", abs(token_cost(e, f) - 0.35) < 1e-9, token_cost(e, f))
    check("完全不同给 1.0", token_cost(char_tokens("天")[0], char_tokens("狗")[0]) == 1.0)
    check("完全相同给 0", token_cost(char_tokens("天")[0], char_tokens("天")[0]) == 0.0)


def test_dtw_small():
    print("[半全局 DTW]")
    P = char_tokens("今天想跟你聊一个很多家长都问过我的问题")
    q = char_tokens("跟你聊一个很多家长")
    score, end = semiglobal_dtw(P, q)
    check("干净匹配代价为 0", abs(score) < 1e-9, score)
    check("终点落在 q 最后一个字之后", P[end - 1] == q[-1], (end, P[end - 1] if end else None))

    # 从中间开始念：起点自由
    q2 = char_tokens("很多家长都问过")
    score2, end2 = semiglobal_dtw(P, q2)
    check("起点自由（从中间开始也能对齐）", abs(score2) < 1e-9, score2)
    check("终点正确", P[end2 - 1] == q2[-1], end2)


def test_exact():
    print("[正确读]")
    s, a = make()
    # 前 24 个字念完
    lo, hi = 0, 24
    q = chars_of(s, lo, hi)
    r = a.update(q)
    check("整段对齐位置正确", r.pos == expect_after(s, hi), f"pos={r.pos} 期望={expect_after(s, hi)}")
    check("置信度高", r.conf > 0.9, r.conf)

    # 再往后念，位置应该往前走。注意 46 正好是逗号，要一起跳过
    hi2 = 46
    r2 = a.update(chars_of(s, hi - 10, hi2))
    check("继续往后念位置前进", r2.pos == expect_after(s, hi2), f"pos={r2.pos} 期望={expect_after(s, hi2)}")
    check("停在逗号处时逗号也变灰", r2.pos > 45, r2.pos)
    check("delta 为正", r2.delta > 0, r2.delta)


def test_punct_shift():
    print("[标点不得让位置偏移]")
    s, a = make()
    # 故意从一段带很多标点的地方开始
    lo, hi = 8, 40
    q = chars_of(s, lo, hi)
    punct = sum(1 for c in s.chars[lo:hi] if c.is_punct)
    r = a.update(q)
    want = expect_after(s, hi)
    check(f"含 {punct} 个标点仍精确落位", r.pos == want, f"pos={r.pos} 期望={want}")


def test_homophone():
    print("[同音字]")
    s, a = make()
    lo, hi = 0, 20
    q = chars_of(s, lo, hi)
    # 把「是」换成「事」——ASR 常见错误
    q_bad = q.replace("是", "事")
    a.update(chars_of(s, 0, 10))
    r = a.update(q_bad)
    check("同音替换不破坏对齐", abs(r.pos - hi) <= 1, f"pos={r.pos} 期望≈{hi}")
    check("同音替换后仍有置信度", r.conf > 0.7, r.conf)


def test_missing():
    print("[漏字]")
    s, a = make()
    lo, hi = 0, 26
    q = chars_of(s, lo, hi)
    # 去掉中间一个字，模拟 ASR 漏听
    q_miss = q[:8] + q[9:]
    r = a.update(q_miss)
    check("漏一个字仍能落位", abs(r.pos - hi) <= 2, f"pos={r.pos} 期望≈{hi}")


def test_extra():
    print("[多字]")
    s, a = make()
    lo, hi = 0, 26
    q = chars_of(s, lo, hi)
    # 中间插一个语气词，模拟 ASR 多听
    q_extra = q[:10] + "啊" + q[10:]
    r = a.update(q_extra)
    check("多一个字仍能落位", abs(r.pos - hi) <= 2, f"pos={r.pos} 期望≈{hi}")


def test_jump():
    print("[跳句]")
    s, a = make()
    # 这一条验的是「DTW 在窗口内找得到远处那个位置」，不是位移上限 —— 所以关掉上限，
    # 否则 72 字的跳读会被 5 行（70 字）夹住。上限本身由 test_jump_limit 负责。
    a.max_jump_lines = 0
    a.reset(0)
    a.update(chars_of(s, 0, 12))
    # 用户直接跳到很后面（但仍在 lookahead 内）
    lo, hi = 60, 84
    r = a.update(chars_of(s, lo, hi))
    check("跳读能追上去", r.pos == expect_after(s, hi), f"pos={r.pos} 期望={expect_after(s, hi)}")
    check("跳读 delta 明显为正", r.delta > 30, r.delta)


def test_noise():
    print("[噪音 / 无关内容]")
    s, a = make()
    a.reset(20)
    before = a.pos
    r = a.update("今天天气不错我要出去吃饭了顺便买点水果回来")
    check("无关内容不移动位置", r.pos == before, f"pos={r.pos} 期望={before}")
    check("无关内容置信度低于门限", r.conf < 0.45, r.conf)

    r2 = a.update("嗯")
    check("过短输入直接忽略", r2.pos == before, r2.pos)


def test_back_hysteresis():
    print("[回退迟滞]")
    s, a = make()
    a.reset(30)
    # 低置信度下大幅回退 → 应被按住
    r = a.update("完全无关的一段话在这里出现了")
    check("低置信不回退", r.pos >= 30 - a.back_step_max, f"pos={r.pos}")

    # 高置信度下回退 → 允许（念错了要能修）
    slot = chars_of(s, 20, 34)
    r2 = a.update(slot)
    check("高置信允许回退修正", r2.pos == expect_after(s, 34), f"pos={r2.pos} 期望={expect_after(s, 34)}")


# ---------------------------------------------------------------- 跳跃限制（v2.3.0）
# 用 TEXT 打底再接五句互不相同的正文：既够长（>210 字），又不会出现"整篇同一个句子"，
# 否则 DTW 在每个副本上代价都是 0，测出来的东西和"位移上限"根本没关系。
LONG = TEXT + (
    "为什么会这样？因为他在重复已经会的东西，回避真正不会的东西。"
    "抄错题是体力活，想明白错在哪才是脑力活。"
    "所以第一件事是别急着加量，先看看孩子的时间到底花在了哪儿。"
    "今天晚上回去，你可以让他把今天做的题分成三类：会做的、蒙对的、完全不会的。"
    "分完你就知道问题在哪了。这个动作只要十分钟，比你报三个补习班都有用。"
)


def test_jump_limit():
    """单次位移不得超过 max_jump_lines 行。

    ⛔ 这是需求 B 的核心回归。对齐器一拍能在 pos-40 ~ pos+100 字里自由落点，
    稿子里有重复句子时会锁到远处那个副本；按 14 字/行算一次能蹿 7 行，
    0.3 秒滑过去 —— 用户看到的就是「大幅上下滚动，偏离正在读的地方」。
    """
    print("[跳跃限制]")
    s = Script.from_text(LONG, 14)
    per = s.per_line
    check("测试稿够长（≥ 210 字）", len(s.chars) >= 210, len(s.chars))

    limit = 5 * per                        # 5 行 × 14 字
    pos0 = 100
    # 终点落在搜索窗口内（≤ pos0 + lookahead=100），起点远在 5 行之外 ——
    # 正好是"不夹就会蹿出去"的那个位置关系。
    lo2, hi2 = pos0 + 78, pos0 + 99
    q = chars_of(s, lo2, hi2)
    want = expect_after(s, hi2)

    # ① 先证明"不限制时确实会蹿很远"。这一步要是失败，说明 DTW 压根没找到远处的位置，
    #    那下面所有"被夹住了"的断言都是空过 —— 必须让它先叫出来。
    a = Aligner(s)
    a.max_jump_lines = 0
    a.reset(pos0)
    r = a.update(q)
    check(f"不限时确实往前蹿了 {r.delta} 字", r.pos > pos0 + limit, f"pos={r.pos}")

    # ② 5 行上限：同一段输入，一拍只能到 pos0 + limit
    a.max_jump_lines = 5
    a.reset(pos0)
    r = a.update(q)
    check("5 行上限把单拍位移夹住", r.pos == pos0 + limit, f"pos={r.pos} 期望={pos0 + limit}")
    check("delta 与夹后的位置一致", r.delta == limit, r.delta)

    # ③ 不是卡死：连续几拍照样能追上去（3 Hz × 5 行 ≈ 210 字/秒，肉眼看是"滑过去"）
    for _ in range(6):
        a.update(q)
    check("连续几拍能自己追到目标", abs(a.pos - want) <= 1, f"pos={a.pos} 期望={want}")

    # ④ 往回退也夹。注意窗口是 -40/+100 不对称的，回退天然最多 40 字上下，
    #    用 5 行（70 字）根本够不着，所以这一条得用 1 行（14 字）才夹得住。
    slot = chars_of(s, 0, 20)
    a.max_jump_lines = 1
    a.reset(40)
    r = a.update(slot)
    check("1 行上限时夹住回退", r.pos >= 40 - per, f"pos={r.pos}")

    a.max_jump_lines = 0                   # 同一次输入，不限时应该一步退到底
    a.reset(40)
    r0 = a.update(slot)
    check("不限时回退是完整的（不是本来就退不动）", r0.pos == expect_after(s, 20), f"pos={r0.pos}")

    # ⑤ 0 = 不限，行为与 v2.2.4 完全一致
    a.max_jump_lines = 0
    a.reset(pos0)
    r = a.update(q)
    check("0 = 不限（回到 v2.2.4 行为）", r.pos == want, f"pos={r.pos} 期望={want}")


def test_jump_invariant():
    """无论从哪儿开始念、念到哪一段，单拍位移都不越界。

    比单点用例更狠：这里拿「同一段话重复三遍」的稿子扫一遍 —— 那正是用户报的场景，
    重复副本会让 DTW 在多个等代价位置之间摇摆。
    """
    print("[跳跃限制 · 不变量]")
    s = Script.from_text(TEXT * 3, 14)
    a = Aligner(s)
    a.max_jump_lines = 5
    limit = 5 * s.per_line
    worst = 0
    starts = 0
    for start in range(0, max(1, len(s.chars) - 30), 7):
        starts += 1
        a.reset(start)
        for off in (0, 30, 60, 90, 130):       # 越往后越容易锁到远处的重复副本
            lo = start + off
            hi = min(lo + 18, len(s.chars))
            if hi - lo < 4:
                continue
            r = a.update(chars_of(s, lo, hi))
            worst = max(worst, abs(r.delta))
    check(f"扫 {starts} 个起点，单拍位移从未超过 {limit} 字", worst <= limit, f"最大 {worst} 字")


def test_jump_limit_session():
    """ui 里的「最大跟进」要真的传到对齐器上，包括运行中改值和 rebuild。"""
    print("[跳跃限制 · 接进会话]")
    from app import config
    from app.session import Session

    ui = dict(config.DEFAULT_UI)
    ui["follow_mode"] = "ai"
    ui["max_jump_lines"] = 8
    s = Session(ui, LONG)
    check("构造时就同步了最大跟进", s.aligner.max_jump_lines == 8, s.aligner.max_jump_lines)

    s.start()
    ui["max_jump_lines"] = 2                   # 模拟控制台滑块改了 ui
    s.feed_asr(chars_of(s.script, 0, 20))
    check("改 ui 后下一拍就生效", s.aligner.max_jump_lines == 2, s.aligner.max_jump_lines)

    ui["max_jump_lines"] = 0
    s.rebuild()                                # rebuild 会 new 一个 Aligner，别落回默认值
    check("rebuild 之后仍跟着 ui", s.aligner.max_jump_lines == 0, s.aligner.max_jump_lines)

    # 老 state.json 里没有这个键时，不能 KeyError，要退回 DEFAULT_UI
    ui2 = {k: v for k, v in config.DEFAULT_UI.items() if k != "max_jump_lines"}
    ui2["follow_mode"] = "ai"
    s2 = Session(ui2, LONG)
    check("ui 缺这个键时退回默认值",
          s2.aligner.max_jump_lines == config.DEFAULT_UI["max_jump_lines"],
          s2.aligner.max_jump_lines)


def test_session_follow():
    """对齐器接到会话上：两种推进方式的切换与互斥。"""
    print("[推进方式切换]")
    from app import config
    from app.session import Session

    ui = dict(config.DEFAULT_UI)
    s = Session(ui, TEXT)
    check("默认是自动滚动", s.mode == "auto", s.mode)

    # --- auto 模式：按速度自己走，识别结果一概不吃 ---
    s.start()
    q = "".join(c.ch for c in s.script.chars[0:26])
    check("auto 模式忽略识别结果", s.feed_asr(q) is None)
    before = s.pos
    for _ in range(30):
        s.tick(1 / 60)
    check("auto 模式按速度推进", s.pos > before + 1, (before, s.pos))
    s.stop()

    # --- ai 模式：不走时间轴，只认识别结果 ---
    ui["follow_mode"] = "ai"
    s.start()
    before = s.pos
    for _ in range(60):
        s.tick(1 / 60)
    check("ai 模式不自己滚动", abs(s.pos - before) < 1e-9, (before, s.pos))
    check("还没接上时 aligned=False", s.aligned is False)

    msg = s.feed_asr(q)
    check("feed_asr 返回位置消息", msg is not None and msg["type"] == "pos", msg)
    check("AI 已接上", s.aligned is True)
    check("位置已推进", abs(s.aligner.pos - expect_after(s.script, 26)) <= 1, s.aligner.pos)

    before = s.pos
    for _ in range(30):
        s.tick(1 / 60)
    check("接上之后心跳仍不自走", abs(s.pos - before) < 1e-9, (before, s.pos))

    s.stop()
    check("stop 回到起点并清 aligned", s.pos == 0.0 and s.aligned is False, (s.pos, s.aligned))
    check("IDLE 时不吃识别结果", s.feed_asr(q) is None)

    # 滚轮是"人接管"：对齐器锚点要跟着挪，否则下一拍会被拉回去
    s.start()
    s.feed_asr(q)
    s.wheel(-1)
    check("滚轮后对齐器锚点同步", s.aligner.pos == int(s.pos), (s.aligner.pos, s.pos))

    # 从 auto 切到 ai：锚点要重对到当前位置，否则第一拍会把画面拽回去
    ui["follow_mode"] = "auto"
    s.start()
    for _ in range(120):        # 让 auto 跑一段
        s.tick(1 / 60)
    cur = int(s.pos)
    ui["follow_mode"] = "ai"
    s.on_mode_changed()
    check("切到 ai 时对齐器重锚到当前位置", s.aligner.pos == cur, (s.aligner.pos, cur))


def main():
    test_cost()
    test_dtw_small()
    test_exact()
    test_punct_shift()
    test_homophone()
    test_missing()
    test_extra()
    test_jump()
    test_noise()
    test_back_hysteresis()
    test_jump_limit()
    test_jump_invariant()
    test_jump_limit_session()
    test_session_follow()
    print(f"\n通过 {OK}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
