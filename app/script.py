"""稿件解析：清洗 → 硬切行 → 注音 → 字符表。

行的定义（v1.3 起）：每行 <= per_line 个字，行是渲染与染色的最小单位。
"""
from __future__ import annotations

from dataclasses import dataclass

from pypinyin import Style, lazy_pinyin

BREAK_PUNCT = set("，。！？；：、,.!?;:")
NO_LINE_START = set("，。！？；：、）》〉”’…·,.!?;:)]}")
ALL_PUNCT = BREAK_PUNCT | set("（）《》〈〉“”‘’—…·-()[]\"'~`!@#$%^&*_+=|\\/<>?")


def _clean(text: str) -> str:
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    blank = False
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            if out and not blank:
                out.append("")
            blank = True
        else:
            out.append(line)
            blank = False
    return "\n".join(out).strip()


def split_lines(text: str, per_line: int) -> list[str]:
    """按 per_line 硬切；优先在标点后断，其次避开英文单词中间。"""
    lines: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        i, n = 0, len(para)
        while i < n:
            end = min(i + per_line, n)
            if end < n:
                window = para[i:end]
                cut = 0
                # 只在行尾 30% 内找标点，否则宁可硬切——
                # 阈值太低会把"大家好，我是老张。"这种 9 字句单独占一行，浪费版面
                floor = max(1, int(per_line * 0.70))
                for k in range(len(window) - 1, floor - 1, -1):
                    if window[k] in BREAK_PUNCT:
                        cut = k + 1
                        break
                if cut:
                    end = i + cut
                elif (
                    para[end - 1].isascii()
                    and para[end].isascii()
                    and para[end - 1].isalnum()
                    and para[end].isalnum()
                ):
                    sp = para.rfind(" ", i, end)
                    if sp > i:
                        end = sp + 1
            seg = para[i:end].strip()
            if seg:
                lines.append(seg)
            i = end
    # 避头：行首不允许出现收尾标点，把它拉回上一行（允许溢出 1–2 字）
    for k in range(1, len(lines)):
        while lines[k] and lines[k][0] in NO_LINE_START and len(lines[k - 1]) < per_line + 1:
            lines[k - 1] += lines[k][0]
            lines[k] = lines[k][1:]
    return [l for l in lines if l]


def _pinyin_columns(chars: str) -> tuple[list[str], list[str], list[str]]:
    n = len(chars)

    def safe(style, strict):
        try:
            vals = lazy_pinyin(chars, style=style, strict=strict, errors=lambda s: list(s))
        except Exception:
            vals = []
        if len(vals) != n:
            vals = [""] * n
        return vals

    return (
        safe(Style.NORMAL, True),
        safe(Style.INITIALS, False),
        safe(Style.FINALS, False),
    )


def char_tokens(text: str) -> list[tuple[str, str]]:
    """任意文本 → 拼音 token 列表，跳过标点与空白。

    给 ASR 结果用。必须和 Script 走同一套切分（`_pinyin_columns`），
    否则稿件侧和识别侧的口径不一致，DTW 会凭空产生代价。
    """
    if not text:
        return []
    _, ini, fin = _pinyin_columns(text)
    out: list[tuple[str, str]] = []
    for ch, i, f in zip(text, ini, fin):
        if ch in ALL_PUNCT or ch.isspace():
            continue
        if "\u4e00" <= ch <= "\u9fff":
            out.append((i or "", f or ""))
        elif ch.isalnum():
            out.append(("", ch.lower()))
    return out


@dataclass
class Char:
    idx: int
    ch: str
    initial: str
    final: str
    is_punct: bool
    line: int


class Script:
    def __init__(self, text: str, chars: list[Char], lines: list[tuple[int, int]], per_line: int):
        self.text = text
        self.chars = chars
        self.lines = lines
        self.per_line = per_line

    # ---------- 构造 ----------
    @classmethod
    def from_text(cls, text: str, per_line: int = 14) -> "Script":
        cleaned = _clean(text)
        line_texts = split_lines(cleaned, per_line)
        joined = "".join(line_texts)
        _, initials, finals = _pinyin_columns(joined)

        chars: list[Char] = []
        lines: list[tuple[int, int]] = []
        idx = 0
        for li, lt in enumerate(line_texts):
            start = idx
            for ch in lt:
                is_p = ch in ALL_PUNCT or ch.isspace()
                if "\u4e00" <= ch <= "\u9fff":
                    ini = initials[idx] or ""
                    fin = finals[idx] or ""
                elif ch.isalnum():
                    ini, fin = "", ch.lower()
                else:
                    ini, fin = "", ""
                chars.append(Char(idx, ch, ini, fin, is_p, li))
                idx += 1
            lines.append((start, idx))
        return cls(cleaned, chars, lines, per_line)

    # ---------- 查询 ----------
    def line_of(self, pos: float) -> int:
        if not self.lines:
            return 0
        p = int(pos)
        for i, (_, end) in enumerate(self.lines):
            if p < end:
                return i
        return len(self.lines) - 1

    def line_start(self, line: int) -> int:
        if not self.lines:
            return 0
        line = max(0, min(line, len(self.lines) - 1))
        return self.lines[line][0]

    def line_len(self, line: int) -> int:
        if not self.lines:
            return 0
        line = max(0, min(line, len(self.lines) - 1))
        s, e = self.lines[line]
        return e - s

    def line_texts(self) -> list[str]:
        return ["".join(c.ch for c in self.chars[s:e]) for s, e in self.lines]

    def pinyin_window(self, lo: int, hi: int) -> list[tuple[str, str]]:
        lo = max(0, lo)
        hi = min(len(self.chars), hi)
        return [(c.initial, c.final) for c in self.chars[lo:hi] if not c.is_punct]

    def token_window(self, lo: int, hi: int) -> tuple[list[tuple[str, str]], list[int]]:
        """同 pinyin_window，但**同时返回每个 token 对应的字索引**。

        对齐器必须用这个：pinyin_window 过滤掉了标点，返回的下标和 `chars`
        不再一一对应，直接拿 DP 终点当位置会偏出标点那么多个字。
        """
        lo = max(0, lo)
        hi = min(len(self.chars), hi)
        toks: list[tuple[str, str]] = []
        idxs: list[int] = []
        for c in self.chars[lo:hi]:
            if c.is_punct:
                continue
            toks.append((c.initial, c.final))
            idxs.append(c.idx)
        return toks, idxs

    def to_dict(self) -> dict:
        return {
            "lines": self.line_texts(),
            "per_line": self.per_line,
            "chars": len(self.chars),
            "n_lines": len(self.lines),
        }
