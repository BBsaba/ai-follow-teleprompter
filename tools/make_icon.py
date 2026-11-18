"""生成桌面快捷方式用的图标：黑底圆角方块 + 三条白字线 + 一条红线。

跟提词窗的视觉一致（黑底白字、红线横在文字下方），缩到 32px 也认得出。
产出 assets/teleprompter.ico（多尺寸）。

    python tools/make_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "teleprompter.ico"

BG = (14, 14, 16)          # 近黑，比纯黑更像"界面"
WHITE = (245, 245, 247)
RED = (255, 45, 45)        # 与 config.DEFAULT_UI["cue_color"] 一致
SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size: int) -> Image.Image:
    """按目标尺寸等比绘制，避免小尺寸下线条糊在一起。"""
    s = 256
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 背景：圆角方，留一点边让阴影自然
    d.rounded_rectangle([10, 10, 246, 246], radius=52, fill=BG)

    # 三条文字线；小图标时加粗，否则 16px 下会消失
    line_h = 20 if size >= 32 else 26
    for i, y in enumerate((74, 116, 158)):
        # 第三条略短，像"正在念的这行还没走完"
        right = 196 if i < 2 else 168
        d.rounded_rectangle([54, y, right, y + line_h],
                            radius=line_h // 2, fill=WHITE)

    # 红线：比文字线更宽，像一根横贯的标尺
    cue_h = 12 if size >= 32 else 16
    d.rounded_rectangle([38, 196, 218, 196 + cue_h],
                        radius=cue_h // 2, fill=RED)

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw(n) for n in SIZES]
    # 以最大尺寸为主体，save 时带上其余尺寸
    frames[-1].save(OUT, format="ICO",
                    sizes=[(n, n) for n in SIZES],
                    append_images=frames[:-1])
    print(f"[ok] {OUT}  ({OUT.stat().st_size} 字节, {len(SIZES)} 个尺寸)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
