"""视觉回归：用 Playwright 驱动提词窗，产出关键状态截图。

用法：
    python tests/shot.py            # 拍默认四张
    python tests/shot.py resize     # 只拍窗口适配对比

产出到仓库根目录下的 shots/（已在 .gitignore 里忽略）
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8756"
ROOT = Path(__file__).resolve().parent.parent
OUT = str(ROOT / "shots")
os.makedirs(OUT, exist_ok=True)


def shot(page, name):
    path = f"{OUT}/{name}.png"
    page.screenshot(path=path)
    print(f"  -> {path}")
    return path


def wait_ready(page):
    """等 WebSocket init 到达（.line 节点出现）。"""
    page.wait_for_selector("#text .line", timeout=8000)
    page.wait_for_timeout(250)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                                  device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: print(f"    [console.{m.type}] {m.text}"))
        page.on("pageerror", lambda e: print(f"    [pageerror] {e}"))

        # ---------- 1. 准备态 ----------
        page.goto(f"{BASE}/prompter", wait_until="domcontentloaded")
        wait_ready(page)
        if only in (None, "idle"):
            shot(page, "p1-idle")

        # ---------- 2. 跟读中（空格开始，跑 2.5 秒） ----------
        page.keyboard.press("Space")
        page.wait_for_timeout(2500)
        if only in (None, "run"):
            shot(page, "p2-run")

        # ---------- 3. 滚轮选行（向下 3 格 → 当前行下移） ----------
        for _ in range(3):
            page.mouse.move(640, 360)
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(120)
        page.wait_for_timeout(400)
        if only in (None, "wheel"):
            shot(page, "p3-wheel-down")

        # 检查染色：上方行应全灰，当前行及以下应全白（当前行已读部分除外）
        diag = page.evaluate(
            """() => {
              const lines = [...document.querySelectorAll('#text .line')];
              const cur = lines.findIndex(el => !el.classList.contains('read')
                                              && el.querySelector('.ch.read'));
              // 更稳的做法：从 DOM 里反推当前行
              let curLine = -1;
              for (let i = 0; i < lines.length; i++) {
                const n = lines[i].querySelectorAll('.ch.read').length;
                if (n > 0 && n < lines[i].children.length) { curLine = i; break; }
              }
              const readFlags = lines.map(el => el.classList.contains('read'));
              // 上方行：应全部 read=true
              const above = readFlags.slice(0, curLine);
              const below = readFlags.slice(curLine + 1);
              return {
                nLines: lines.length,
                curLine,
                allAboveGrey: above.every(Boolean),
                anyBelowGrey: below.some(Boolean),
                transform: getComputedStyle(document.getElementById('text')).transform,
                cueTop: document.getElementById('cue').getBoundingClientRect().top,
                curLineBottom: curLine >= 0
                  ? lines[curLine].getBoundingClientRect().bottom : null,
                stageH: document.getElementById('stage').clientHeight,
              };
            }"""
        )
        print(f"  [diag] {diag}")

        # ---------- 4. 暂停态 ----------
        page.keyboard.press("Space")
        page.wait_for_timeout(300)
        if only in (None, "pause"):
            shot(page, "p4-paused")

        # ---------- 5. 窗口尺寸适配 ----------
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        for w, h in [(960, 540), (1600, 900), (720, 900)]:
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(400)
            rect = page.evaluate(
                """() => {
                  const stage = document.getElementById('stage');
                  const cue = document.getElementById('cue').getBoundingClientRect();
                  const lines = [...document.querySelectorAll('#text .line')];
                  const fs = parseFloat(getComputedStyle(document.documentElement)
                                        .getPropertyValue('--fs'));
                  // 文本层水平是否居中
                  const t = document.getElementById('text').getBoundingClientRect();
                  return {
                    stageW: stage.clientWidth, stageH: stage.clientHeight,
                    cueTopPct: +(cue.top / stage.clientHeight * 100).toFixed(1),
                    fs, nLines: lines.length,
                    textLeftPct: +(t.left / stage.clientWidth * 100).toFixed(1),
                    textRightPct: +((t.right) / stage.clientWidth * 100).toFixed(1),
                    overflowX: t.width > stage.clientWidth,
                  };
                }"""
            )
            print(f"  [resize {w}x{h}] {rect}")
            if only in (None, "resize"):
                shot(page, f"p5-{w}x{h}")

        browser.close()


if __name__ == "__main__":
    main()
