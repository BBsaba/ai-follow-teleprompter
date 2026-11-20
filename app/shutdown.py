"""关掉整个程序：一个共享的「退出」开关。

为什么单独开一个模块：uvicorn 的 `Server` 对象在 `run.py` 里创建，
而「退出」请求是从 `app/server.py` 的 HTTP 路由进来的。两边直接互相 import
会成环，所以中间放这么一个小小的中转站 —— 它只认一个对象、只做一件事。

为什么不用信号（`os.kill` / `signal.raise_signal`）：信号处理器只在主线程装得上，
而且 Windows 上 `CTRL_C_EVENT` 只对控制台进程组有效 —— 我们恰恰最需要它工作的
那种情况（`pythonw` 无控制台）根本送不进去。直接置位 `Server.should_exit`
是 uvicorn 自己认的旗子，与有没有控制台无关。
"""
from __future__ import annotations

import os
import threading
import time

#: uvicorn 的 Server 实例，run.py 启动时绑上来
_server = None

#: 已经有人按过「退出」了。防连点：第二次请求直接返回，别开第二个线程
_quitting = False

#: 置位旗子之后等多久还没退干净就直接硬退（秒）。
#: 有它兜底是因为优雅退出要跑 lifespan 的 finally（`listener.stop()`，
#: 里面在关音频流、等识别线程收尾）——万一那一步卡住，用户按了「退出」
#: 却什么都没发生，就又回到「点了没反应」的老问题上了。
HARD_EXIT_AFTER = 8.0


def bind(server) -> None:
    """把 uvicorn 的 Server 绑进来。只该在 run.py 里调一次。"""
    global _server
    _server = server


def is_quitting() -> bool:
    return _quitting


def request_quit(delay: float = 0.35) -> None:
    """请服务在 delay 秒后退出。调用方可以立刻返回响应。

    为什么要延迟：这个函数是从 HTTP 处理函数里调的。当场退出会让浏览器
    那个请求拿不到响应，前端只能显示「网络错误」—— 用户会以为点坏了。
    先让响应发出去，再收摊。
    """
    global _quitting
    if _quitting:
        return
    _quitting = True

    srv = _server

    def _later() -> None:
        time.sleep(delay)
        if srv is None:
            # 极端情况：服务不是由 run.py 起的（比如开发时 uvicorn 命令行直接跑）。
            # 那时候没有 Server 可置位，硬退也胜过「按了没反应」。
            os._exit(0)
        srv.should_exit = True
        time.sleep(HARD_EXIT_AFTER)
        os._exit(0)          # 走到这儿说明优雅退出没成功，兜底

    threading.Thread(target=_later, name="quit", daemon=True).start()
