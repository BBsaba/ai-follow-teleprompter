"""UI 集成测试：控制台联动 / 提词窗渲染 / 窗口自适应。

前置：服务已在 127.0.0.1:8756 运行（python run.py）
运行：NO_PROXY="*" python tests/test_ui.py
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8756"
ok = 0
bad = 0

# 固定测试稿：切行相关的断言（行数随每行字数变化）必须有确定的输入，
# 否则"上一次测试留下的当前稿件"会悄悄改变结果——实测踩过：短稿下
# 14 字/行和 10 字/行切出来都是 7 行，断言直接失败。
FIXTURE_ID = "_ui_fixture"
FIXTURE_TEXT = ("这是一段用于界面测试的固定稿件，长度足够切出十几行，"
                "让每一行字数的变化都能在行数上看出来。" * 4)


def chk(name: str, cond: bool, extra: str = "") -> None:
    global ok, bad
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        bad += 1
        print(f"  FAIL  {name}  {extra}")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 860})
        page = ctx.new_page()
        errs: list[str] = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        # 先把参数复位，避免上轮遗留的字号/红线把断言带偏
        page.goto(f"{BASE}/prompter", wait_until="domcontentloaded")
        page.evaluate(
            """async () => {
              await fetch('/api/state', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ font_px: 64, per_line: 14, cue_ratio: 0.42, mirror: false, follow_mode: 'auto' }),
              });
            }"""
        )
        page.wait_for_timeout(300)
        # 换成固定稿件，别看用户当前在写哪篇
        page.evaluate(
            """async (args) => {
              await fetch('/api/scripts', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: args.id, text: args.text }),
              });
            }""",
            {"id": FIXTURE_ID, "text": FIXTURE_TEXT},
        )
        page.goto(f"{BASE}/console", wait_until="domcontentloaded")
        page.wait_for_timeout(1400)

        # ---------- 1. 提词窗基础渲染 ----------
        print("[1] 提词窗渲染")
        frame = page.frame_locator("#preview")
        n_lines = frame.locator("#text .line").count()
        chk("稿件已切行", n_lines > 5, f"n_lines={n_lines}")
        first_txt = frame.locator("#text .line").first.text_content()
        chk("首行无行首标点", first_txt[0] not in "，。！？；：、）》”’", first_txt)

        geo = frame.locator(":root").evaluate(
            """() => {
              const stage = document.getElementById('stage');
              const lines = [...document.querySelectorAll('#text .line')];
              const cue = document.getElementById('cue').getBoundingClientRect();
              const r0 = lines[0].getBoundingClientRect();
              return {stageH: stage.clientHeight, cueTop: cue.top,
                      l0top: r0.top, l0bot: r0.bottom};
            }"""
        )
        gap = geo["cueTop"] - geo["l0bot"]
        chk("红线贴当前行底边(≤10px)", 0 <= gap <= 10, f"gap={gap:.1f}")

        # ---------- 2. 字号 / 每行 联动 ----------
        print("[2] 参数联动")
        fs0 = frame.locator(":root").evaluate(
            '() => getComputedStyle(document.documentElement).getPropertyValue("--fs")'
        ).strip()
        page.eval_on_selector(
            "#rFont", "el => { el.value = 96; el.dispatchEvent(new Event('input',{bubbles:true})); }"
        )
        page.wait_for_timeout(500)
        fs1 = frame.locator(":root").evaluate(
            '() => getComputedStyle(document.documentElement).getPropertyValue("--fs")'
        ).strip()
        chk("字号下发到提词窗", fs0 != fs1, f"{fs0} -> {fs1}")

        n1 = frame.locator("#text .line").count()
        page.eval_on_selector(
            "#rPer", "el => { el.value = 10; el.dispatchEvent(new Event('input',{bubbles:true})); }"
        )
        page.wait_for_timeout(700)
        n2 = frame.locator("#text .line").count()
        chk("每行改小 → 行数变多", n2 > n1, f"{n1} -> {n2}")

        # 还原
        page.eval_on_selector(
            "#rPer", "el => { el.value = 14; el.dispatchEvent(new Event('input',{bubbles:true})); }"
        )
        page.eval_on_selector(
            "#rFont", "el => { el.value = 64; el.dispatchEvent(new Event('input',{bubbles:true})); }"
        )
        page.wait_for_timeout(700)

        # ---------- 3. 录制态锁定 ----------
        print("[3] 两态模型")
        page.click("#btnStart")
        page.wait_for_timeout(700)
        st = page.evaluate(
            """() => ({
              mode: document.getElementById('modeTag').textContent,
              font: document.getElementById('rFont').disabled,
              per: document.getElementById('rPer').disabled,
              sel: document.getElementById('scripts').disabled,
              ro: document.getElementById('text').readOnly,
            })"""
        )
        chk("录制中 = 跟读中", st["mode"] == "跟读中", st["mode"])
        chk("录制中 字号锁定", st["font"] is True)
        chk("录制中 每行锁定", st["per"] is True)
        chk("录制中 稿件选择锁定", st["sel"] is True)
        chk("录制中 正文只读", st["ro"] is True)

        page.click("#btnStart")
        page.wait_for_timeout(500)
        st2 = page.evaluate(
            """() => ({mode: document.getElementById('modeTag').textContent,
                       font: document.getElementById('rFont').disabled,
                       ro: document.getElementById('text').readOnly})"""
        )
        chk("停止后 回到待机", st2["mode"] == "待机", st2["mode"])
        chk("停止后 控件解锁", st2["font"] is False and st2["ro"] is False)

        # ---------- 4. 提词窗：窗口自适应 ----------
        print("[4] 提词窗自适应")
        pp = ctx.new_page()
        pp.on("pageerror", lambda e: errs.append("prompter:" + str(e)))
        pp.goto(f"{BASE}/prompter", wait_until="domcontentloaded")
        pp.wait_for_selector("#text .line")
        pp.wait_for_timeout(300)

        for w, h in [(960, 540), (1280, 720), (1600, 900), (720, 900)]:
            pp.set_viewport_size({"width": w, "height": h})
            pp.wait_for_timeout(320)
            m = pp.evaluate(
                """() => {
                  const stage = document.getElementById('stage');
                  const cue = document.getElementById('cue').getBoundingClientRect();
                  const t = document.getElementById('text').getBoundingClientRect();
                  return {cuePct: cue.top / stage.clientHeight * 100,
                          leftPct: t.left / stage.clientWidth * 100,
                          rightPct: t.right / stage.clientWidth * 100,
                          over: t.width > stage.clientWidth + 1};
                }"""
            )
            chk(f"{w}x{h} 红线落在比例位", abs(m["cuePct"] - 42) < 1.5, f"{m['cuePct']:.1f}%")
            chk(f"{w}x{h} 左右居中", abs((m["leftPct"] + (100 - m["rightPct"])) / 2 - m["leftPct"]) < 1.0,
                f"{m['leftPct']:.1f}/{m['rightPct']:.1f}")
            chk(f"{w}x{h} 无横向溢出", m["over"] is False)

        # ---------- 5. 滚轮选行 ----------
        print("[5] 滚轮选行")
        pp.set_viewport_size({"width": 1280, "height": 720})
        pp.wait_for_timeout(250)
        pp.keyboard.press("Space")
        pp.wait_for_timeout(600)
        pp.mouse.move(640, 360)
        for _ in range(2):
            pp.mouse.wheel(0, 120)
            pp.wait_for_timeout(140)
        pp.wait_for_timeout(300)
        r = pp.evaluate(
            """() => {
              const lines = [...document.querySelectorAll('#text .line')];
              let cur = -1;
              for (let i = 0; i < lines.length; i++) {
                const n = lines[i].querySelectorAll('.ch.read').length;
                if (n > 0 && n < lines[i].children.length) { cur = i; break; }
              }
              const grey = lines.map(el => el.classList.contains('read'));
              return {cur, aboveAllGrey: grey.slice(0, cur).every(Boolean),
                      belowAnyGrey: grey.slice(cur + 1).some(Boolean),
                      curGrey: grey[cur]};
            }"""
        )
        chk("滚轮已移动当前行", r["cur"] > 0, f"cur={r['cur']}")
        chk("上方行全部变灰", r["aboveAllGrey"] is True)
        chk("当前行及以下不变灰", r["belowAnyGrey"] is False and r["curGrey"] is False)

        # ---------- 6. 录制态按键拦截 ----------
        print("[6] 录制态按键")
        before = pp.evaluate("() => document.getElementById('hint').classList.contains('show')")
        pp.keyboard.press("KeyA")
        pp.keyboard.press("Digit1")
        pp.wait_for_timeout(200)
        after = pp.evaluate("() => document.getElementById('hint').classList.contains('show')")
        chk("无关键位不触发暂停", before == after, f"{before}->{after}")

        pp.keyboard.press("Space")
        pp.wait_for_timeout(300)
        chk("空格触发暂停", pp.evaluate(
            "() => document.getElementById('cue').classList.contains('paused')") is True)

        pp.keyboard.press("Escape")
        pp.wait_for_timeout(300)
        chk("Esc 退出到待机", pp.evaluate(
            "() => !document.getElementById('cue').classList.contains('paused')") is True)

        # ---------- 7. AI 状态提示 + 删除 ----------
        print("[7] AI 状态与删除")
        page.goto(f"{BASE}/console", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        # 布局回归：窗口矮的时候，预览框曾经压住模式开关，点都点不到
        for w, h in [(1440, 900), (1280, 800), (1100, 720)]:
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(220)
            hit = page.evaluate(
                """() => {
                  const s = document.getElementById('segMode').getBoundingClientRect();
                  const e = document.elementFromPoint(s.left + 20, s.top + 10);
                  return e ? (e.id || e.className || e.tagName) : null;
                }"""
            )
            chk(f"{w}x{h} 模式开关没被预览框盖住", hit in ("btnModeAuto", "segMode"), str(hit))

        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_timeout(300)

        page.click("#btnModeAi")
        page.wait_for_timeout(500)
        chk("AI 模式出现状态条", page.locator("#aiStatus").is_visible())
        ai_txt = page.locator("#aiStatus").inner_text()
        chk("未开麦时明说'麦克风没开'", "麦克风没开" in ai_txt, ai_txt)
        chk("状态条标为警示态", "off" in (page.locator("#aiStatus").get_attribute("class") or ""))

        page.click("#btnModeAuto")          # 回到 auto，避免自动开麦拖慢测试
        page.wait_for_timeout(400)
        chk("自动滚动时不显示 AI 状态条", not page.locator("#aiStatus").is_visible())

        chk("有删除按钮", page.locator("#btnDel").count() == 1)
        chk("待机时删除按钮可用", page.locator("#btnDel").is_enabled())

        page.click("#btnStart")
        page.wait_for_timeout(700)
        chk("录制中删除按钮被锁定", page.locator("#btnDel").is_disabled())
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        chk("退出后删除按钮恢复", page.locator("#btnDel").is_enabled())

        # 真删一篇：造稿 → 选中 → 删 → 确认列表少一项且自动切走
        page.evaluate(
            """async () => {
              await fetch('/api/scripts', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: '_ui_tmp_del', text: '界面删除用的临时稿。' }),
              });
            }"""
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1100)
        page.select_option("#scripts", "_ui_tmp_del")
        page.wait_for_timeout(600)
        n_before = page.locator("#scripts option").count()

        page.on("dialog", lambda d: d.accept())
        page.click("#btnDel")
        page.wait_for_timeout(1300)
        ids = page.eval_on_selector_all("#scripts option", "els => els.map(e => e.value)")
        chk("删除后列表少一项", len(ids) == n_before - 1, f"{n_before} -> {len(ids)}")
        chk("临时稿已消失", "_ui_tmp_del" not in ids, str(ids))
        chk("自动切到别的稿件且有正文", len(page.locator("#text").input_value()) > 0)

        # 清掉测试稿，别留在用户的稿件列表里
        page.evaluate(
            """async (id) => {
              await fetch('/api/scripts/' + encodeURIComponent(id), { method: 'DELETE' });
            }""",
            FIXTURE_ID,
        )
        page.wait_for_timeout(300)

        chk("全程无 JS 报错", not errs, str(errs[:3]))
        browser.close()

    print(f"\n通过 {ok}，失败 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
