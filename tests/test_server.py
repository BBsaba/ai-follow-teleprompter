"""服务层单测：稿件存储 + "AI 模式开始要不要自动开麦"。

不启动服务、不加载模型、不碰麦克风 —— 纯把逻辑跑一遍，毫秒级。
真正的端到端（真识别、真跟随）在 test_live.py / test_follow_e2e.py 里。

    python tests/test_server.py
"""
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, server, store  # noqa: E402

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


# ---------------- 稿件 id 安全 ----------------
def test_sid_guard():
    print("[稿件 id 校验]")
    for good in ("demo", "口播稿", "a-b_c", "2026-11-17 早课", "x1"):
        check(f"接受 {good!r}", store.is_valid_sid(good))

    # 这些能拼出工程外的路径，或者 Windows 不许做文件名的字符
    for bad in ("../secret", "..\\win", "a/b", "a\\b", "..", ".hidden",
                "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b", "", "  ", "x" * 81):
        check(f"拒绝 {bad!r:.20}", not store.is_valid_sid(bad))


# ---------------- 删除稿件 ----------------
def test_delete_script():
    print("[删除稿件]")
    with tempfile.TemporaryDirectory() as td:
        old = config.SCRIPTS_DIR
        config.SCRIPTS_DIR = Path(td)
        try:
            store.write_script("keep", "留着")
            store.write_script("gone", "删掉")

            check("删除存在的稿", store.delete_script("gone") is True)
            check("文件真的没了", not (Path(td) / "gone.md").exists())
            check("别的稿没被牵连", (Path(td) / "keep.md").exists())

            check("删不存在的返回 False", store.delete_script("gone") is False)
            check("非法 id 不会被删", store.delete_script("../app/config") is False)
            check("非法 id 没伤到外面", (ROOT / "app" / "config.py").exists())
        finally:
            config.SCRIPTS_DIR = old


# ---------------- AI 模式自动开麦 ----------------
def _patch_listener(calls):
    """把 listener.start 换成记账用的假函数，别真去开麦。"""
    orig = server.listener.start

    async def fake():
        calls.append(1)

    server.listener.start = fake
    return orig


def _restore(orig):
    server.listener.start = orig
    server.session.stop()
    server.listener.on = False
    server.listener.loading = False


def test_auto_ear():
    print("[AI 模式开始 → 自动开麦]")
    ui = server.session.ui
    old_mode = ui.get("follow_mode")
    orig = _patch_listener(calls := [])

    async def go(msg):
        await server._dispatch(msg)
        await asyncio.sleep(0.05)      # create_task 要一个循环周期才跑到

    try:
        ui["follow_mode"] = "ai"
        server.listener.on = False
        server.listener.loading = False
        calls.clear()
        asyncio.run(go({"type": "start"}))
        check("ai 模式下点开始 → 调了 listener.start", len(calls) == 1, calls)

        server.session.stop()
        calls.clear()
        asyncio.run(go({"type": "start"}))
        check("每次开始都会检查（而不是只在第一次）", len(calls) == 1, calls)

        # 已经开着就不该重复开
        server.session.stop()
        calls.clear()
        server.listener.on = True
        asyncio.run(go({"type": "start"}))
        check("麦克风已开时不重复开麦", len(calls) == 0, calls)

        # 加载中也不该叠加第二次
        server.session.stop()
        calls.clear()
        server.listener.on = False
        server.listener.loading = True
        asyncio.run(go({"type": "start"}))
        check("加载中不重复触发", len(calls) == 0, calls)

        # auto 模式绝不能偷偷开麦
        server.listener.loading = False
        ui["follow_mode"] = "auto"
        server.session.stop()
        calls.clear()
        asyncio.run(go({"type": "start"}))
        check("auto 模式开始不会开麦", len(calls) == 0, calls)

        # 暂停/继续不该重新开麦
        ui["follow_mode"] = "ai"
        calls.clear()
        asyncio.run(go({"type": "pause"}))
        check("暂停不碰麦克风", len(calls) == 0, calls)
    finally:
        _restore(orig)
        if old_mode:
            ui["follow_mode"] = old_mode


# ---------------- 磁盘占用接口 ----------------
def test_storage_api():
    """`/api/storage` 与 `/api/storage/clean`。

    重点不是"能删日志"，是**不能删别的东西** —— 白名单比黑名单可靠：
    将来 storage 里多了一个新清理函数，也不会因为漏配一个 if 就变成
    可以从浏览器调用的删除器。
    """
    print("[磁盘占用接口]")
    from app import storage

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        old_logs, old_cache = config.LOG_FILES, storage.INSTALL_CACHE_DIR
        config.LOG_FILES = (tmp / "data" / "launch.log",)
        storage.INSTALL_CACHE_DIR = tmp / "_tmp"
        try:
            (tmp / "data").mkdir(parents=True)
            (tmp / "data" / "launch.log").write_text("x" * 64, "utf-8")
            (tmp / "data" / "launch.log.1").write_text("y" * 64, "utf-8")

            st = asyncio.run(server.api_storage())
            rows = {r["key"]: r for r in st["rows"]}
            check("有日志这一行", "logs" in rows, list(rows))
            check("日志 2 个文件 128 字节",
                  rows["logs"]["count"] == 2 and rows["logs"]["bytes"] == 128, rows["logs"])

            r = asyncio.run(server.api_storage_clean({"what": "logs"}))
            check("清理日志返回 ok", r.get("ok") is True, r)
            after = {x["key"]: x for x in r["storage"]["rows"]}["logs"]
            check("清理后日志行归零", after["bytes"] == 0 and after["count"] == 0, after)
            check("两个文件都不在了",
                  not (tmp / "data" / "launch.log").exists()
                  and not (tmp / "data" / "launch.log.1").exists())

            # ⛔ 白名单：稿件永远不在可清理范围里
            bad = asyncio.run(server.api_storage_clean({"what": "scripts"}))
            check("传 scripts 被拒（400）", getattr(bad, "status_code", None) == 400, bad)
            bad2 = asyncio.run(server.api_storage_clean({}))
            check("不传 what 也被拒（400）", getattr(bad2, "status_code", None) == 400, bad2)
            bad3 = asyncio.run(server.api_storage_clean({"what": "../../etc"}))
            check("路径样的名字也被拒", getattr(bad3, "status_code", None) == 400, bad3)
        finally:
            config.LOG_FILES, storage.INSTALL_CACHE_DIR = old_logs, old_cache


def main():
    test_sid_guard()
    test_delete_script()
    test_auto_ear()
    test_storage_api()
    print(f"\n通过 {OK}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
