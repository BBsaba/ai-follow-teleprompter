"""集成冒烟：需要先启动服务（默认 127.0.0.1:8756）。

    python tests/test_ws.py
"""
import asyncio
import json
import os
import sys

# 本地回环绝不该走代理。公司机器常全局设 HTTP_PROXY，
# 新版 websockets 会照着走，于是连 127.0.0.1 也被代理拒掉（502）。
os.environ["NO_PROXY"] = "127.0.0.1,localhost," + os.environ.get("NO_PROXY", "")
os.environ["no_proxy"] = os.environ["NO_PROXY"]

import websockets

URL = "ws://127.0.0.1:8756/ws"
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


async def collect(ws, seconds):
    out = []
    try:
        async with asyncio.timeout(seconds):
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") == "pos":
                    out.append(msg["pos"])
    except (asyncio.TimeoutError, TimeoutError):
        pass
    return out


async def main():
    # 本节断言依赖"自动滚动"推进位置。测试不能指望用户上次选的是哪个模式，
    # 所以先显式置成 auto，跑完再还原。
    import urllib.request
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def put(patch: dict) -> dict:
        req = urllib.request.Request(
            f"http://127.0.0.1:8756/api/state",
            data=json.dumps(patch).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        return json.loads(op.open(req).read())

    original_mode = put({})["ui"].get("follow_mode", "auto")
    put({"follow_mode": "auto"})

    async with websockets.connect(URL) as ws:
        init = json.loads(await ws.recv())
        check("init 收到", init["type"] == "init")
        check("稿件有行", len(init["script"]["lines"]) > 3, init["script"]["n_lines"])
        check("init 带 ui", "cue_ratio" in init["ui"])

        await ws.send(json.dumps({"type": "start"}))
        frames = await collect(ws, 2.0)
        check("start 后有推进", len(frames) >= 3, len(frames))
        first, last = frames[0], frames[-1]
        check("行号单调不减", last["line"] >= first["line"], (first, last))
        check("行内进度前进", (last["line"], last["readIdx"]) > (first["line"], first["readIdx"]),
              (first, last))

        await ws.send(json.dumps({"type": "pause"}))
        paused = await collect(ws, 0.6)
        check("暂停后 state=PAUSED", any(p["state"] == "PAUSED" for p in paused) or paused == [],
              paused[-1] if paused else None)

        before = paused[-1] if paused else last
        await ws.send(json.dumps({"type": "wheel", "delta": 3}))
        down = await collect(ws, 0.6)
        check("滚轮向下进 3 行", down and down[-1]["line"] == before["line"] + 3,
              (before, down[-1] if down else None))
        check("滚轮后行内清零", down and down[-1]["readIdx"] == 0,
              down[-1] if down else None)

        await ws.send(json.dumps({"type": "wheel", "delta": -1}))
        up = await collect(ws, 0.6)
        check("滚轮向上退 1 行", up and up[-1]["line"] == (before["line"] + 3) - 1,
              (down[-1] if down else None, up[-1] if up else None))

        await ws.send(json.dumps({"type": "stop"}))
        stopped = await collect(ws, 0.6)
        check("stop 回 IDLE", stopped and stopped[-1]["state"] == "IDLE",
              stopped[-1] if stopped else None)
        check("stop 回到首行", stopped and stopped[-1]["line"] == 0,
              stopped[-1] if stopped else None)

    put({"follow_mode": original_mode})     # 还原用户原来的选择
    print(f"\n通过 {OK}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
