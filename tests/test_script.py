"""不依赖 pytest，直接 `python tests/test_script.py` 即可。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.motion import Motion
from app.script import NO_LINE_START, Script, split_lines

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


def test_wrap():
    print("[切行]")
    text = "大家好，我是老张。今天想跟你聊一个很多家长都问过我的问题：孩子明明很努力，成绩却一直上不去。"
    lines = split_lines(text, 14)
    check("每行不超过 15 字（避头悬挂允许 +1）", all(len(l) <= 15 for l in lines), [len(l) for l in lines])
    check("行数 > 1", len(lines) > 1, len(lines))
    check("不丢字", "".join(lines) == text.replace("\n", ""), "".join(lines))

    # 行尾标点优先：逗号落在第 13 位，应在逗号后断
    l2 = split_lines("一二三四五六七八九十十一，十二十三", 14)
    check("行尾标点优先断行", l2[0] == "一二三四五六七八九十十一，", l2)

    # 句中靠前的标点不该导致提前断行（否则 9 字就占一行）
    l3 = split_lines("大家好，我是老张。今天想跟你聊一个很多家长都问过我的问题", 14)
    check("靠前标点不提前断行", len(l3[0]) == 14, l3[0])

    # 英文单词不被切断
    l4 = split_lines("hello world foobar baz", 12)
    check("英文按空格断", all(not l.endswith(" ") for l in l4) and len(l4) > 1, l4)

    # 避头：行首不能是收尾标点
    l5 = split_lines("今天想跟你聊一个很多家长都问过我的问题：孩子明明很努力", 14)
    check("行首无标点", all(not l or l[0] not in NO_LINE_START for l in l5), l5)
    check("避头不丢字", "".join(l5) == "今天想跟你聊一个很多家长都问过我的问题：孩子明明很努力",
          "".join(l5))


def test_script():
    print("[Script]")
    s = Script.from_text("今天天气不错，我们开始录课。", per_line=8)
    check("chars 非空", len(s.chars) > 0, len(s.chars))
    check("lines 非空", len(s.lines) > 0, len(s.lines))
    check("line_texts 长度一致", len(s.line_texts()) == len(s.lines))

    for i, (a, b) in enumerate(s.lines):
        check(f"行{i} 区间合法", 0 <= a < b <= len(s.chars), (a, b))

    p = 3
    line = s.line_of(p)
    check("line_of 命中", s.lines[line][0] <= p < s.lines[line][1], (p, line))
    check("line_start 与 line_of 自洽", s.line_start(line) <= p)

    # 最后一行越界保护
    check("越界取末行", s.line_of(9999) == len(s.lines) - 1)

    han = [c for c in s.chars if "\u4e00" <= c.ch <= "\u9fff"]
    check("汉字有拼音", all(c.final for c in han), [(c.ch, c.final) for c in han][:5])

    empty = Script.from_text("", per_line=14)
    check("空稿不崩", empty.lines == [] and empty.line_of(0) == 0)


def test_motion():
    print("[Motion]")
    m = Motion()
    m.snap(0)
    for _ in range(120):
        d = m.step(10, 1 / 60)
    check("收敛到目标", abs(d - 10) < 0.5, d)

    m.snap(10)
    for _ in range(120):
        m.step(0, 1 / 60)
    check("后退也收敛", m.d < 1.0, m.d)


if __name__ == "__main__":
    test_wrap()
    test_script()
    test_motion()
    print(f"\n通过 {OK}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
