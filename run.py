"""启动：起本地服务并打开控制台。

端口上已经有本程序在跑（上一次没关干净）时，不报错崩掉，直接打开那个实例。
用 HTTP 探测而不是 socket.bind 试探——TIME_WAIT 会让 bind 误判成"被占用"。

依赖没装齐时，这里给一段人话说明，而不是甩一整屏 ModuleNotFoundError。

安装版会自动换用自带的运行时：双击 run.py 时 Windows 用 py.exe 启动器挑
系统里的 Python，那个当然没装本项目的依赖。所以真跑之前先看一眼 ——
安装目录里若自带 python 运行时，就切过去重跑（见 _reexec_with_bundled_python）。
这样双击 run.py、双击快捷方式、从任意 Python 里跑，结果都是同一套依赖。

桌面和开始菜单的快捷方式走的是 pythonw.exe（不弹黑框），它**没有控制台**，
sys.stdout / sys.stderr 都是 None。这不是小事，见 _ensure_streams 的说明。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

# 起服务必需：(import 名, pip 包名)
# torch / transformers / qwen_asr 故意不在此列——它们只在点「开始」加载模型时
# 才 import（见 app/asr.py 的 load），缺了也不该挡着打开界面。这个分层是刻意的：
# 没有模型也该能写字、看稿、调字号。
#
# websockets 也必须查：uvicorn 裸装不带 ws 实现，缺了它页面照常打开、字也能显示，
# 但红线和文字一动不动——症状像"程序坏了"，其实只差一个包。
_REQUIRED = (
    ("numpy", "numpy"),
    ("sounddevice", "sounddevice"),
    ("pypinyin", "pypinyin"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("websockets", "websockets"),
)

#: 已经换过一次解释器的标记，防止来回重启
_REEXEC_FLAG = "AITP_REEXEC"

#: 启动时是不是「没有控制台」（pythonw）。决定出错时该 print 还是该弹窗。
_HEADLESS = False

#: 单实例互斥体的名字。⛔ 必须和 installer\AI提词器.iss 里的 `AppMutex` 一字不差，
#: 否则安装程序认不出「提词器正在运行」，又会退回到逐个文件弹「拒绝访问」。
_MUTEX_NAME = "AITeleprompterRunning"

#: 互斥体句柄。必须留着不关 —— 句柄一关，互斥体就没了，进程还活着也没用。
_mutex_handle = None


def _hold_instance_mutex() -> None:
    """声明「提词器正在运行」，让安装程序能提前发现。

    为什么需要它（v2.2.3 修的真实事故）：安装时如果程序正开着，`pythonw.exe`
    已经把 `python313.dll`、`libcrypto-3.dll`、`_ssl.pyd` 这些加载进内存，
    Windows 不允许删除被映射的文件，Inno 的 DeleteFile 就报「错误代码 5 拒绝访问」。
    而 Inno 是**逐个文件**弹框（重试 / 跳过 / 取消安装）—— 用户看到的是几十个
    弹窗排队，只能一个个点「跳过」，装完还是个新旧混杂的目录。

    有了这个互斥体，`[Setup] AppMutex` 在向导出现之前就能发现它，只弹**一次**
    「请先退出提词器」。

    注意：已经存在时 CreateMutex 会返回 ERROR_ALREADY_EXISTS 但**仍是有效句柄**，
    所以绝不能把它当失败 —— 双击两下快捷方式时第二份就是要走这条路。
    """
    global _mutex_handle
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        _mutex_handle = k32.CreateMutexW(None, False, _MUTEX_NAME)
    except Exception:
        # 拿不到就拿不到：最坏情况是退回旧行为（安装时逐文件弹框），
        # 不该因为这个连程序都起不来。
        _mutex_handle = None


def _ensure_streams() -> Path | None:
    """没有控制台时，给 sys.stdout / sys.stderr 接上一个真实的文件。

    为什么非接不可 —— 这是 v2.2.0「点快捷方式毫无反应」的真正原因：

    pythonw.exe 是 GUI 子系统程序，没有控制台，于是 sys.stdout / sys.stderr
    都是 None。uvicorn（0.54）配置日志时会算 self.use_colors = sys.stdout.isatty()，
    在 None 上取属性直接抛 AttributeError，logging 配置失败，于是 uvicorn.run()
    **还没开始监听端口**就抛 ValueError 退出。
    而这时候 stderr 也是 None —— 那个 traceback 连一个字都没地方写。
    用户双击快捷方式，屏幕上什么都不会发生，任务管理器里也看不到进程。

    接到 data/launch.log 还有第二个好处：以后再出任何岔子，那个文件里躺着完整
    的调用栈，不用再靠猜。装到不可写目录时退到 %TEMP%，再不行就 os.devnull ——
    关键是 sys.stdout 必须是个有 isatty() 的对象，哪怕它把字都扔掉。
    """
    global _HEADLESS
    _HEADLESS = sys.stdout is None or sys.stderr is None

    sink = None
    log_path: Path | None = None
    for cand in (
        Path(__file__).resolve().parent / "data" / "launch.log",
        Path(os.environ.get("TEMP") or ".") / "AITeleprompter-launch.log",
    ):
        try:
            cand.parent.mkdir(parents=True, exist_ok=True)
            # 追加而不是覆盖：已经有一个实例在跑时，再点一次快捷方式也会走到这里。
            # 用 "w" 会把正在跑的那个实例的启动记录抹掉，日志反而没用了。
            sink = open(cand, "a", encoding="utf-8", buffering=1)
            log_path = cand
            break
        except OSError:
            sink = None
    if sink is None:
        sink = open(os.devnull, "w", encoding="utf-8")

    if sys.stdout is None:
        sys.stdout = sink
    if sys.stderr is None:
        sys.stderr = sink

    if log_path is not None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{stamp}] ─── 启动 ───")
        print(f"[{stamp}] 程序   {sys.executable}")
        print(f"[{stamp}] 目录   {Path(__file__).resolve().parent}")
        print(f"[{stamp}] 控制台 {'无（pythonw）' if _HEADLESS else '有'}")
        print(f"[{stamp}] Python {sys.version.split()[0]}")
    return log_path


def _notify(message: str, error: bool = False) -> None:
    """出事了要让用户看见。

    有控制台就 print；pythonw 下 print 是空操作（sys.stdout 被接到文件里了，
    弹不出字来），只能弹窗。沉默失败是上一版最糟的地方：用户点了快捷方式，
    屏幕上什么都没有，也不知道该去哪儿看。
    """
    try:
        print(message)
    except Exception:
        pass
    if not _HEADLESS:
        return
    try:
        import ctypes

        flags = 0x10 if error else 0x40          # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, message, "AI 提词器", flags)
    except Exception:                            # 连弹窗都失败就算了，别二次崩
        pass


def _bundled_python() -> Path | None:
    """安装目录里的自带解释器；在源码目录里跑时返回 None。"""
    own = Path(__file__).resolve().parent / "python" / "python.exe"
    return own if own.is_file() else None


def _reexec_with_bundled_python() -> None:
    """安装版把自己切到自带的 python.exe 再继续。

    为什么需要：.py 在 Windows 上关联给 py.exe 启动器，它按 PATH 和注册表挑
    系统里装的 Python。用户明明刚用安装包装好，双击 run.py 却得到一屏
    「依赖没装齐 + 去建 venv」的教程 —— 那条路根本不适合安装版。

    判断「已经在对的解释器里」比的是**目录**不是文件名：桌面快捷方式用的是
    pythonw.exe（无控制台），它和 python.exe 同目录，不该被判定成需要重启。
    """
    own = _bundled_python()
    if own is None:
        return                                   # 源码目录，没有自带运行时
    try:
        if Path(sys.executable).resolve().parent == own.parent.resolve():
            return                               # 已经是 python.exe / pythonw.exe
    except OSError:
        pass
    if os.environ.get(_REEXEC_FLAG) == "1":
        return                                   # 防死循环

    try:
        print(f"[提词器] 改用自带运行时：{own}")
    except Exception:                            # 控制台编码古怪时别为此崩掉
        pass
    env = dict(os.environ)
    env[_REEXEC_FLAG] = "1"
    # 用 call 而非 os.exec*：Windows 上 exec* 和 POSIX 差得远，
    # 而且这里想等子进程结束、把它的退出码原样带出去。
    raise SystemExit(subprocess.call([str(own), str(Path(__file__).resolve())], env=env))


def _missing_deps() -> list[str]:
    """返回缺的 pip 包名。find_spec 不执行模块，比 import 快且不会触发 CUDA 初始化。"""
    missing = []
    for mod, pkg in _REQUIRED:
        try:
            if importlib.util.find_spec(mod) is None:
                missing.append(pkg)
        except (ImportError, ValueError):   # 模块在，但自身的导入链坏了
            missing.append(pkg)
    return missing


def _explain_missing(missing: list[str]) -> None:
    print()
    print("[提词器] 依赖没装齐，服务起不来。缺这几样：")
    print("         " + "、".join(missing))
    print()
    print("[提词器] 现在用的是：")
    print(f"         {sys.executable}")
    print(f"         Python {sys.version.split()[0]}")
    print()

    if _bundled_python() is not None:
        # 安装版：绝不能再教用户「python -m venv」—— 他没有源码，
        # 也不该在安装目录里自己造一套依赖。那是开发者的路。
        print("[提词器] 这是安装版，把依赖补齐就行：")
        print()
        print("   ① 重新运行安装程序（同一个安装包、装到同一个目录），它会补上缺的包。")
        print()
        print("   ② 想先看卡在哪，在本目录执行：")
        print("        python\\python.exe -m pip install -r requirements.txt")
        print()
        print("   ③ 装完还缺，用开始菜单里的「排查启动」看完整报错。")
        print()
        return

    print("[提词器] 三选一：")
    print()
    print("   ① 最省事 —— 双击本目录的 setup.bat，装完再双击 start.bat。")
    print()
    print("   ② 手动装（在本目录执行）：")
    print("        python -m venv .venv")
    print("        .venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    print()
    print("   ③ 你别的 venv 里已经装好了，就让提词器改用它：")
    print('        setx TELEPROMPTER_PYTHON "D:\\某个venv\\Scripts\\python.exe"')
    print("      然后关掉本窗口，重新双击 start.bat。")
    print()


def _url(host: str, port: int) -> str:
    return f"http://{host}:{port}/"


def _already_running(url: str) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 绕开系统代理
    try:
        with opener.open(f"{url}api/state", timeout=0.8) as r:
            return r.status == 200
    except Exception:
        return False


def _open(url: str) -> None:
    """稍等启动完成再开浏览器；开不出来就说清楚地址，别让人干等。"""
    time.sleep(1.2)
    try:
        ok = webbrowser.open(url)
    except Exception:
        ok = False
    if not ok:
        _notify(
            "服务已经起来了，但没能自动打开浏览器。\n\n"
            f"手动打开这个地址即可：\n{url}"
        )


def main() -> None:
    log_path = _ensure_streams()

    try:                                   # 输出重定向到文件时也别攒着
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    missing = _missing_deps()
    if missing:
        _explain_missing(missing)
        # pythonw 下上面那些 print 全进了文件，用户一个字也看不到 —— 必须弹窗
        _notify(
            "提词器打不开：运行环境缺了这几个包。\n\n"
            "    " + "、".join(missing) + "\n\n"
            "重新运行安装程序（同一个安装包、装到同一个目录）就会补齐。",
            error=True,
        )
        try:
            input("按回车关闭窗口 …")
        except Exception:                  # 无控制台时 input() 会抛 RuntimeError
            pass
        raise SystemExit(1)

    import uvicorn                      # 依赖确认后才 import，否则就白炸了

    from app import config, shutdown
    from app.server import app

    url = _url(config.HOST, config.PORT)

    if _already_running(url):
        print(f"[提词器] {config.PORT} 端口上已有实例在跑，直接打开 {url}")
        print("[提词器] 要重启请先关掉旧窗口。")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        time.sleep(1.2)
        raise SystemExit(0)

    print(f"[提词器] 控制台   {url}")
    print(f"[提词器] 提词窗   {url}prompter")
    if _HEADLESS:
        # pythonw 没有窗口可关 —— 照抄「关掉本窗口」会让人到处找不到那个窗口
        print("[提词器] 后台运行：没有控制台窗口，要停止请在任务管理器结束 pythonw.exe")
    else:
        print("[提词器] 关掉本窗口即停止服务。")
    threading.Thread(target=_open, args=(url,), daemon=True).start()

    # 从这里开始就算「在运行」了：文件马上要被锁在内存里，
    # 安装程序靠这个互斥体提前发现，避免逐文件报「拒绝访问」。
    _hold_instance_mutex()

    # 这里自己建 Config/Server，不调 uvicorn.run()：只有拿到 Server 对象，
    # 控制台的「退出程序」按钮才能把 should_exit 置位（见 app/shutdown.py）。
    # uvicorn.run() 内部正是这么建的，行为一致，只是那个对象没人拿得到。
    uv_cfg = uvicorn.Config(app, host=config.HOST, port=config.PORT, log_level="warning")
    server = uvicorn.Server(uv_cfg)
    shutdown.bind(server)

    try:
        server.run()
        print("[提词器] 已退出")
    except OSError as e:
        print(f"[提词器] 启动失败：{e}")
        print(f"[提词器] {config.PORT} 端口可能被别的程序占了，"
              f"改端口见 app/config.py 的 PORT。")
        _notify(
            f"提词器启动失败：{e}\n\n"
            f"{config.PORT} 端口可能被别的程序占用了。\n"
            "关掉占用它的程序再试一次。",
            error=True,
        )
        try:
            input("按回车关闭…")
        except Exception:
            pass
    except Exception:
        # 兜底：任何非 OSError 的启动异常都要落到日志 + 弹窗，不许静默消失
        detail = traceback.format_exc()
        print(detail)
        _notify(
            "提词器启动失败，下面是出错的地方：\n\n"
            + traceback.format_exc(limit=4)
            + (f"\n\n完整记录：{log_path}" if log_path else ""),
            error=True,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        # 必须在 main() 之前：依赖检查和 import app 都要在正确的解释器里做
        _reexec_with_bundled_python()
        main()
    except SystemExit:
        raise
    except BaseException:
        # 最后一道网。走到这儿说明连 main() 都没撑住 —— 多半是 import 期就炸了，
        # 那时候 _ensure_streams 还没跑，stderr 可能还是 None，所以直接写文件。
        detail = traceback.format_exc()
        for cand in (
            Path(__file__).resolve().parent / "data" / "launch.log",
            Path(os.environ.get("TEMP") or ".") / "AITeleprompter-launch.log",
        ):
            try:
                cand.parent.mkdir(parents=True, exist_ok=True)
                with open(cand, "a", encoding="utf-8") as f:
                    f.write("\n[崩溃] " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + detail)
                break
            except OSError:
                continue
        _notify("提词器没能启动：\n\n" + detail[-900:], error=True)
        raise
