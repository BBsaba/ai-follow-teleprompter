"""启动：起本地服务并打开控制台。

端口上已经有本程序在跑（上一次没关干净）时，不报错崩掉，直接打开那个实例。
用 HTTP 探测而不是 socket.bind 试探——TIME_WAIT 会让 bind 误判成"被占用"。

依赖没装齐时，这里给一段人话说明，而不是甩一整屏 ModuleNotFoundError。
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import time
import urllib.request
import webbrowser

# 起服务必需：(import 名, pip 包名)
# torch / transformers / qwen_asr 故意不在此列——它们只在点「开始」加载模型时
# 才 import（见 app/asr.py 的 load），缺了也不该挡着打开界面。这个分层是刻意的：
# 没有模型也该能写字、看稿、调字号。
_REQUIRED = (
    ("numpy", "numpy"),
    ("sounddevice", "sounddevice"),
    ("pypinyin", "pypinyin"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
)


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
    time.sleep(1.2)
    webbrowser.open(url)


def main() -> None:
    try:                                   # 输出重定向到文件时也别攒着
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    missing = _missing_deps()
    if missing:
        _explain_missing(missing)
        try:
            input("按回车关闭窗口 …")
        except EOFError:
            pass
        raise SystemExit(1)

    import uvicorn                      # 依赖确认后才 import，否则就白炸了

    from app import config
    from app.server import app

    url = _url(config.HOST, config.PORT)

    if _already_running(url):
        print(f"[提词器] {config.PORT} 端口上已有实例在跑，直接打开 {url}")
        print("[提词器] 要重启请先关掉旧窗口。")
        webbrowser.open(url)
        time.sleep(1.2)
        raise SystemExit(0)

    print(f"[提词器] 控制台   {url}")
    print(f"[提词器] 提词窗   {url}prompter")
    print("[提词器] 关掉本窗口即停止服务。")
    threading.Thread(target=_open, args=(url,), daemon=True).start()
    try:
        uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")
    except OSError as e:
        print(f"[提词器] 启动失败：{e}")
        print(f"[提词器] {config.PORT} 端口可能被别的程序占了，"
              f"改端口见 app/config.py 的 PORT。")
        input("按回车关闭…")


if __name__ == "__main__":
    main()
