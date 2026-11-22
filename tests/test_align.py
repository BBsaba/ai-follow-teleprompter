"""对齐器单测。`python tests/test_align.py`

覆盖规划里点名的五类情况：正确 / 漏字 / 多字 / 同音 / 跳句，
外加两条回归：标点不得让位置偏移、噪音不得乱跳。

v2.4 起「跳句」的语义换成了**跟随范围**：只在当前位置前后各 N 行里找，
范围外一律不跟（见 test_range_*）。
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
    score, end, skips = semiglobal_dtw(P, q)
    check("干净匹配代价为 0", abs(score) < 1e-9, score)
    check("终点落在 q 最后一个字之后", P[end - 1] == q[-1], (end, P[end - 1] if end else None))
    check("完整匹配没有跳过任何识别字", skips == 0, skips)

    # 从中间开始念：起点自由
    q2 = char_tokens("很多家长都问过")
    score2, end2, skips2 = semiglobal_dtw(P, q2)
    check("起点自由（从中间开始也能对齐）", abs(score2) < 1e-9, score2)
    check("终点正确", P[end2 - 1] == q2[-1], end2)
    check("起点自由不产生跳过", skips2 == 0, skips2)

    # 窗口装不下整句：装不下的部分只能跳过，skips 要数得出来、终点要贴边。
    # 这两个数正是 _match 判「窗口截断」的依据，缺一个都拦不住跨窗跳读。
    P3 = char_tokens("今天想跟你聊一个")
    q3 = char_tokens("今天想跟你聊一个很多家长都问过我的问题")
    _, end3, skips3 = semiglobal_dtw(P3, q3)
    check(f"窗口装不下时 skips 报出被跳过的字数（{skips3}）", skips3 >= 8, skips3)
    check("被挤掉时终点贴在窗口末尾", end3 == len(P3), (end3, len(P3)))


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


# ---------------------------------------------------------------- 跟随范围（v2.4）
# 用 TEXT 打底再接五句互不相同的正文：既够长（>210 字），又不会出现"整篇同一个句子"，
# 否则 DTW 在每个副本上代价都是 0，测出来的东西和「范围」根本没关系。
LONG = TEXT + (
    "为什么会这样？因为他在重复已经会的东西，回避真正不会的东西。"
    "抄错题是体力活，想明白错在哪才是脑力活。"
    "所以第一件事是别急着加量，先看看孩子的时间到底花在了哪儿。"
    "今天晚上回去，你可以让他把今天做的题分成三类：会做的、蒙对的、完全不会的。"
    "分完你就知道问题在哪了。这个动作只要十分钟，比你报三个补习班都有用。"
)


def test_range_inside():
    """范围以内：立刻跟过去，一拍到位（不再有任何限速）。"""
    print("[跟随范围 · 范围内]")
    s = Script.from_text(LONG, 14)
    per = s.per_line
    a = Aligner(s)
    a.follow_lines = 8
    a.reset(20)
    # 跳 4 行 = 56 字，落在 ±8 行（112 字）里
    lo = 20 + per * 4
    q = chars_of(s, lo, lo + 16)
    r = a.update(q)
    check(f"范围内跳读一拍跟上（pos={r.pos}）", r.pos == expect_after(s, lo + 16),
          f"pos={r.pos} 期望={expect_after(s, lo + 16)}")
    check("没有报「超出范围」", r.over == 0, r.over)


def test_range_outside():
    """范围以外：不跟，位置一动不动 —— 这正是用户要的「跳太远的部分不跟」。"""
    print("[跟随范围 · 范围外]")
    s = Script.from_text(LONG, 14)
    per = s.per_line
    a = Aligner(s)
    a.follow_lines = 4                      # ±4 行 = ±56 字
    a.reset(20)
    lo = 20 + per * 10                      # 跳 10 行 = 140 字，远超范围
    q = chars_of(s, lo, lo + 16)
    before = a.pos
    r = a.update(q)
    check("超范围不跟（位置没动）", r.pos == before, f"pos={r.pos} 期望={before}")
    check(f"报出了「超出范围」且方向朝前（over={r.over}）", r.over > 0, r.over)
    check("over 大致等于真实差距", abs(r.over - (lo + 16 - before)) <= per,
          f"over={r.over} 实际差距={lo + 16 - before}")

    # 同一个人，接着在范围外读 —— 仍然不跟，且不许被拖到窗口边缘
    for k in range(5):
        a.update(chars_of(s, lo + k * 5, lo + k * 5 + 16))
    check("持续在范围外读也不会被拖走", abs(a.pos - before) <= per,
          f"pos={a.pos} before={before}")


def test_range_straddle():
    """识别片段「前半句在范围内、后半句在范围外」：不许被贴到窗口边缘跟过去。

    ⛔ 这条是用户实测报上来的（2026-11-21）：范围设 3 行（42 字），屏幕却从开头
    跳到了第 7 行。根因不是范围算错，而是**窗口截断被当成了成功匹配** ——
    4 秒滑窗在跳读那一刻同时装着"刚才念的"和"现在念的"，后半句已经在窗外；
    DTW 把装不下的部分逐字跳过（gap_asr 仅 0.85/字，而且因为窗内有的是同音字，
    跳过的位置是**散在路径中间**的），代价不高 → 置信度 0.6~0.9 → 看着像成功
    匹配，落点正好在窗口边缘。下一拍真正的目标就进了窗口，两拍走完一次大跳。

    判据不能只看「跳了几个字」：正常跟读碰上 ASR 噪声也能跳到 5~6 个，和跨窗
    片段在 6 上撞车。真正的特征是**路径终点顶在窗口最后一格**——人的下一句已经
    在窗外，DTW 无处可去只能贴边收尾。
    """
    print("[跟随范围 · 跨窗片段]")
    s = Script.from_text(LONG, 14)
    a = Aligner(s)
    a.follow_lines = 3
    r = a.radius()
    check("范围 3 行 = 半径 42 字（下限没有意外抬高它）", r == 42, r)

    hit = 0
    total = 0
    worst = None
    for start in (10, 20, 35, 50):
        for tail in (r + 8, r + 20, r + 40, r + 70):
            a.reset(start)
            q = chars_of(s, start - 6, start + tail)
            res = a.update(q)
            total += 1
            if res.pos != start:                 # 动了就算错
                hit += 1
                if worst is None or abs(res.pos - start) > abs(worst[1] - start):
                    worst = (start, res.pos, tail, res.conf)
    check(f"跨窗片段一处都不许跟过去（{total} 种跨度，动了 {hit} 种）", hit == 0,
          f"最严重：pos {worst[0]}→{worst[1]}（片段到 +{worst[2]}，conf={worst[3]}）"
          if worst else "")

    # 对照：同样从 start 开始，但片段整段落在窗口内 —— 必须跟得上。
    # 没有这一条，上面那条用「什么都不跟」也能通过。
    a.reset(20)
    q = chars_of(s, 20 + 10, 20 + 30)
    res = a.update(q)
    check(f"窗口装得下的片段照常跟（pos={res.pos}）", res.pos == expect_after(s, 50),
          f"pos={res.pos} 期望={expect_after(s, 50)}")


def test_range_script_end():
    """稿子念到最后一句时落点本来就该贴到最后一个字，不能被当成「窗口截断」。

    判据里那个 `hi < n` 就是为这个留的：范围窗口撞到稿子末尾时，边界不是范围
    边界，人真的就在那里。
    """
    print("[跟随范围 · 念到稿尾]")
    s = Script.from_text(LONG, 14)
    n = len(s.chars)
    a = Aligner(s)
    a.follow_lines = 3
    a.reset(n - 30)
    q = chars_of(s, n - 22, n)              # 最后 22 个字
    res = a.update(q)
    check(f"稿尾 22 字照常跟（pos={res.pos} / 结尾 {n}）", res.pos >= n - 6,
          f"pos={res.pos} 期望≈{n}")


def test_range_same_phrase():
    """同一句话在稿子里出现两次、都在范围内：必须选**近的那个**。

    没有「就近优先」这条先验时，两处 DTW 代价完全相等，选谁取决于插入顺序 ——
    实测会选到靠前那一份，屏幕"啪"地往回跳一大段。这是用户最初投诉的形态。
    """
    print("[跟随范围 · 重复句就近]")
    line = "这句话在稿子里出现了两次所以必须认近的那一个"
    filler = "中间这一段是别的内容用来把两份相同的句子隔开不会误配"
    text = line + "。" + filler + "。" + filler + "。" + line + "。"
    s = Script.from_text(text, 14)
    per = s.per_line
    a = Aligner(s)
    a.follow_lines = 10
    # 找第二份的起始字索引
    raw = "".join(c.ch for c in s.chars)
    first_i = raw.find(line[:6])
    second_i = raw.find(line[:6], first_i + 1)
    check("两处副本都在范围内（不然这条测不到东西）",
          second_i - first_i <= a.follow_lines * per, second_i - first_i)
    a.reset(second_i)                       # 人就站在第二份前面
    r = a.update(line[:15])
    check(f"选了近的那份（pos={r.pos}）", abs(r.pos - (second_i + 15)) <= 6,
          f"pos={r.pos} 最近的正确位置={second_i + 15} 远的那份={first_i + 15}")


def test_range_normal_read():
    """正常匀速跟读（每拍几字）绝不能被范围卡住 —— 否则等于用一个大毛病换小毛病。"""
    print("[跟随范围 · 正常跟读]")
    s = Script.from_text(TEXT * 3, 14)
    a = Aligner(s)
    a.follow_lines = 3                      # 最紧的一档（控制台最小值就是 3 行）也能正常读
    a.reset(0)
    fed = 0
    for _ in range(40):                     # 每拍 5 字 ≈ 15 字/秒
        a.update(chars_of(s, fed, fed + 5))
        fed += 5
    check(f"40 拍读 {fed} 字，位置跟上了（pos={a.pos}）", a.pos >= fed - 8,
          f"pos={a.pos} fed={fed}")


def test_range_follows_per_line():
    """范围按「行」算：改每行字数，搜索半径跟着变。"""
    print("[跟随范围 · 跟每行字数走]")
    per = 14
    s = Script.from_text(LONG, per)
    a = Aligner(s)
    a.follow_lines = 6
    back, ahead = a.window()
    check(f"每行 {per} 字 → 半径 {ahead} 字", ahead == 6 * per, ahead)

    s2 = Script.from_text(LONG, 20)
    a2 = Aligner(s2)
    a2.follow_lines = 6
    _, ahead2 = a2.window()
    check(f"每行 20 字 → 半径 {ahead2} 字（同行数、更多字）", ahead2 == 6 * 20, ahead2)


def test_range_min_radius():
    """半径下限：窗口必须装得下「当前这句话」，否则跟读会整体停摆。

    ⛔ 这条是实测补的（2026-11-21）。每行 20 字、范围 1 行 = 半径 20 字时，
    30 字一段的识别结果塞不进窗口，DTW 只能把尾巴挤在窗口边缘、逐字走
    gap_asr，置信度崩到 0.3 以下 —— 喂 900 字只跟到 20 字，而且因为
    「一个字都没动」，界面连「超出范围」都报不出来，用户看到的是「跟读坏了」。
    """
    print("[跟随范围 · 半径下限]")
    s = Script.from_text(LONG, 20)
    a = Aligner(s)
    a.follow_lines = 1                      # 1 行 = 20 字，装不下一段话
    check(f"每行 20 字、范围 1 行 → 半径提到 {a.radius()} 字（不是 20）",
          a.radius() == 60, a.radius())

    s8 = Script.from_text(LONG, 8)          # 每行只有 8 字：3 行 = 24 字还不够
    a8 = Aligner(s8)
    a8.follow_lines = 3
    check(f"每行 8 字、范围 3 行 → 半径兜到 {a8.radius()} 字", a8.radius() == 40, a8.radius())

    a3 = Aligner(s)
    a3.follow_lines = 20                    # 大范围不能被下限干扰
    check(f"范围 20 行仍然是 400 字", a3.radius() == 400, a3.radius())

    # 行为验证：正好走在下限上，30 字一段要能一路跟到底（实测曾在这里停摆）
    b = Aligner(s)
    b.follow_lines = 1
    b.reset(0)
    n = len(s.chars)
    fed = 0
    while fed + 30 <= n:                    # 只喂真实存在的正文，别越过稿尾
        b.update(chars_of(s, fed, fed + 30))
        fed += 30
    check(f"半径下限上 30 字一段也跟得动（跟到 {b.pos}/{fed}）", b.pos >= fed - 60,
          f"pos={b.pos} fed={fed}")


def test_range_zero_falls_back():
    """follow_lines=0（还没接 UI）→ 退回原来的固定窗口，行为不变。"""
    print("[跟随范围 · 0 = 用固定窗口]")
    s = Script.from_text(LONG, 14)
    a = Aligner(s)
    a.follow_lines = 0
    back, ahead = a.window()
    check("退回 lookback/lookahead", (back, ahead) == (a.lookback, a.lookahead),
          (back, ahead))


def test_range_session():
    """ui 里的「跟随范围」要真的传到对齐器上，包括运行中改值和 rebuild。"""
    print("[跟随范围 · 接进会话]")
    from app import config
    from app.session import Session

    ui = dict(config.DEFAULT_UI)
    ui["follow_mode"] = "ai"
    ui["follow_lines"] = 12
    s = Session(ui, LONG)
    check("构造时就同步了跟随范围", s.aligner.follow_lines == 12, s.aligner.follow_lines)

    s.start()
    ui["follow_lines"] = 3                     # 模拟控制台滑块改了 ui
    s.feed_asr(chars_of(s.script, 0, 20))
    check("改 ui 后下一拍就生效", s.aligner.follow_lines == 3, s.aligner.follow_lines)

    ui["follow_lines"] = 20
    s.rebuild()                                # rebuild 会 new 一个 Aligner，别落回默认值
    check("rebuild 之后仍跟着 ui", s.aligner.follow_lines == 20, s.aligner.follow_lines)

    # 老 state.json 里没有这个键时，不能 KeyError，要退回 DEFAULT_UI
    ui2 = {k: v for k, v in config.DEFAULT_UI.items() if k != "follow_lines"}
    ui2["follow_mode"] = "ai"
    s2 = Session(ui2, LONG)
    check("ui 缺这个键时退回默认值",
          s2.aligner.follow_lines == config.DEFAULT_UI["follow_lines"],
          s2.aligner.follow_lines)


def test_range_over_reported():
    """超范围必须能被控制台看见 —— 静默地不跟，就是前几轮反复被投诉的体验。"""
    print("[跟随范围 · 报给控制台]")
    from app import config
    from app.session import Session

    ui = dict(config.DEFAULT_UI)
    ui["follow_mode"] = "ai"
    ui["follow_lines"] = 3
    s = Session(ui, LONG)
    s.start()
    per = s.script.per_line
    start = 20
    s.aligner.reset(start)
    far = start + per * 9
    msg = s.feed_asr(chars_of(s.script, far, far + 18))
    info = s.align_info
    check("这一拍仍然会广播（好让界面更新状态）", msg is not None, msg)
    check(f"align_info 里有 overLines（{info.get('overLines')}）",
          float(info.get("overLines") or 0) >= 5, info)
    check("位置确实没动", int(info["pos"]) == start, info["pos"])


def test_session_follow():
    """对齐器接到会话上：两种推进方式的切换与互斥。"""
    print("[推进方式切换]")
    from app import config
    from app.session import Session

    ui = dict(config.DEFAULT_UI)
    ui["follow_lines"] = 0          # 退回固定窗口，这段测的是「跟随/切换」，不该被范围限位干扰
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
    test_range_inside()
    test_range_outside()
    test_range_straddle()
    test_range_script_end()
    test_range_same_phrase()
    test_range_normal_read()
    test_range_follows_per_line()
    test_range_min_radius()
    test_range_zero_falls_back()
    test_range_session()
    test_range_over_reported()
    test_session_follow()
    print(f"\n通过 {OK}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
