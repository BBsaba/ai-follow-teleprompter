#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构建 Windows 安装程序（Inno Setup）。

一条命令，从零到 dist/ 下的 setup.exe：

    python tools/build_installer.py                # 用 iss 里写死的版本号
    python tools/build_installer.py -v 2.1.1       # 指定版本号
    python tools/build_installer.py --clean        # 先清 build/ 再构建
    python tools/build_installer.py --iscc "D:\\Inno Setup 7\\ISCC.exe"

它做三件事：
  1. 下载官方 Python embeddable 包（约 11 MB），缓存到 build/cache/，
     解压成 payload/python/，改 ._pth，预装 pip（这样用户装的时候不用再下 pip）
  2. 把项目代码拷进 payload/ 根（app/ web/ assets/ run.py …）
  3. 调 ISCC 编译 installer/AI提词器.iss，产物落 dist/

为什么是这台机器上的 Python + Inno Setup，而不是 PyInstaller：
  · embeddable 包就是官方 Python，只是砍掉了测试套件和 tkinter，11 MB；
    用户机器上不需要装 Python，也不需要管理员权限
  · torch 的 CUDA DLL 有 30 多个、3.6 GB，PyInstaller 靠 hook 猜依赖，
    实测会漏文件，装到别人机器上就是运行时 DLL 找不到
  · 安装包最终只有 9 MB 左右 —— 依赖在安装时联网装（这是刻意的：
    「安装程序本身要小」），用户选 CUDA 还是 CPU 决定下 2.6 GB 还是 240 MB

构建机要求：
  · Windows x64
  · Inno Setup 7（或 6）已安装；不在默认路径就用 --iscc 指过去
  · 能访问 python.org、bootstrap.pypa.io（脚本用 urllib，走 OpenSSL，
    不受本机 schannel 吊销检查那套毛病影响）
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
CACHE = BUILD / "cache"
PAYLOAD = BUILD / "payload"
DIST = ROOT / "dist"

PY_VERSION = "3.13.15"
PY_TAG = "".join(PY_VERSION.split(".")[:2])          # 3.13.15 -> 313
EMBED_NAME = f"python-{PY_VERSION}-embed-amd64.zip"
EMBED_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/{EMBED_NAME}"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

#: 进安装包的项目目录（其余不进：docs/tests/.github/.venv/models/data）
INCLUDE_DIRS = ("app", "web", "assets")
#: 进安装包的单文件
INCLUDE_FILES = ("run.py", "requirements.txt", "LICENSE", "README.md")

#: 拷贝时一律跳过
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db", "*.log", ".pytest_cache"
)

#: 给安装后的目录用的启动脚本。安装目录里 python 在 python\ 子目录下，
#: 跟开发目录（.venv 在根）不一样，所以不能直接抄仓库根的那个 start.bat。
LAUNCHER_BAT = r"""@echo off
chcp 65001 >nul
title AI 提词器
cd /d "%~dp0"
rem 这是排查用的启动方式：留着控制台窗口，出错能看到字。
rem 平时请用桌面/开始菜单的快捷方式，那个走 pythonw，不弹黑框。
if not exist "%~dp0python\python.exe" (
    echo [启动器] 找不到 python\python.exe，安装可能不完整，请重新运行安装程序。
    pause
    exit /b 1
)
"%~dp0python\python.exe" "%~dp0run.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo [启动器] 程序退出码 %RC%
    pause
)
exit /b %RC%
"""


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def step(msg: str) -> None:
    print(f"\n== {msg} ==")


def download(url: str, dest: Path, label: str) -> None:
    """下到 dest，已存在就跳过。带进度，失败自动重试 3 次。"""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  缓存命中：{dest.name}（{human(dest.stat().st_size)}）")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")

    for attempt in range(1, 4):
        try:
            print(f"  下载 {label} …")
            with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                t0 = time.time()
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    elapsed = max(time.time() - t0, 0.01)
                    speed = done / elapsed / 1e6
                    if total:
                        pct = done * 100 // total
                        eta = (total - done) / max(done / elapsed, 1)
                        print(
                            f"\r     {pct:3d}%  {human(done)} / {human(total)}"
                            f"  {speed:5.1f} MB/s  剩 {int(eta):3d}s ",
                            end="",
                            flush=True,
                        )
                    else:
                        print(f"\r     {human(done)}  {speed:5.1f} MB/s ", end="", flush=True)
            print()
            tmp.replace(dest)
            return
        except Exception as e:                                    # noqa: BLE001
            print(f"\n  第 {attempt} 次失败：{e}")
            if tmp.exists():
                tmp.unlink()
            if attempt == 3:
                raise SystemExit(
                    f"\n下载失败，放弃：{url}\n"
                    f"可以手动下载后放到 {dest}，再重跑本脚本。"
                ) from e
            time.sleep(2)


def run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    """跑子进程，输出直通（或捕获）。失败抛 SystemExit 并带上输出。"""
    printable = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)
    print(f"  $ {printable}")
    kw = dict(cwd=str(cwd) if cwd else None, text=True)
    if capture:
        kw.update(capture_output=True, encoding="utf-8", errors="replace")
    p = subprocess.run([str(c) for c in cmd], **kw)                # noqa: S603
    out = (p.stdout or "") + (p.stderr or "") if capture else ""
    if capture and out.strip():
        for line in out.strip().splitlines():
            print(f"    {line}")
    if p.returncode != 0:
        raise SystemExit(f"命令失败（退出码 {p.returncode}）：{printable}")
    return out


# --------------------------------------------------------------------------- #
# 1. 运行时
# --------------------------------------------------------------------------- #
def write_pth(rt: Path) -> None:
    """写 embed 包的 `._pth`（那个把 Python 关进隔离模式的开关）。

    ⚠️ 这一步必须**每次构建都跑**，包括 --skip-runtime 复用旧 payload 的时候。
    踩过的坑：某次运行时是在加 `..` 之前生成的，之后十几次构建都用
    --skip-runtime 顺手复用了它，谁也没再看一眼 —— 结果用户装完点开程序
    直接 `ModuleNotFoundError: No module named 'app'`，安装过程却是
    「九个包全部 OK」。装得上 ≠ 跑得起来，差别就在这一行。

    各行的作用：
      python313.zip       stdlib 压缩包
      .                   python\ 目录本身（DLL、_ssl 之类）
      Lib\\site-packages   pip 装的东西
      ..                  项目根 —— 少了它，`import app` 必失败
      import site         不做这步，site-packages 里的包不会被注册
    """
    pth = rt / f"python{PY_TAG}._pth"
    want = f"python{PY_TAG}.zip\n.\nLib\\site-packages\n..\nimport site\n"
    if pth.is_file() and pth.read_text(encoding="utf-8").replace("\r\n", "\n") == want:
        print(f"  {pth.name} 已正确")
        return
    pth.write_text(want, encoding="utf-8", newline="\r\n")
    print(f"  写好 {pth.name}")


def prepare_runtime() -> None:
    rt = PAYLOAD / "python"
    if rt.exists():
        shutil.rmtree(rt)
    rt.mkdir(parents=True)

    embed = CACHE / EMBED_NAME
    download(EMBED_URL, embed, f"Python {PY_VERSION} embeddable (11 MB)")

    print(f"  解压到 {rt.relative_to(ROOT)}")
    with zipfile.ZipFile(embed) as z:
        z.extractall(rt)

    # ._pth 是 embeddable 包的隔离开关：默认只认 zip 和当前目录，
    # 不读系统 site-packages（否则会串到用户机器上装的乱七八糟的包）。
    # 内容与原因见 write_pth()。
    write_pth(rt)

    # 预装 pip：安装时要联网装依赖，pip 得现成。放这里装好，
    # 用户机器上就不用再跑 get-pip（少一次联网、少一个失败点）。
    getpip = CACHE / "get-pip.py"
    download(GET_PIP_URL, getpip, "get-pip.py (2.4 MB)")
    run(
        [
            rt / "python.exe", getpip,
            "--no-warn-script-location",
            "--disable-pip-version-check",
        ],
        cwd=rt,
    )

    # 冒烟：这几样是 stdlib 里最容易因打包缺 DLL 的
    out = run(
        [
            rt / "python.exe", "-c",
            "import ssl, sqlite3, ctypes, zlib, hashlib, urllib.request;"
            "import pip;"
            "print('py', __import__('sys').version.split()[0], '| pip', pip.__version__)",
        ],
        cwd=rt,
        capture=True,
    )
    print(f"  自检通过：{out.strip().splitlines()[-1] if out.strip() else '?'}")


# --------------------------------------------------------------------------- #
# 2. 项目代码
# --------------------------------------------------------------------------- #
def copy_project() -> None:
    for d in INCLUDE_DIRS:
        src = ROOT / d
        if not src.is_dir():
            raise SystemExit(f"缺目录：{src}")
        dst = PAYLOAD / d
        if dst.exists():
            # --skip-runtime 复用 payload 时这里已经有上一轮拷进去的代码，
            # 不清掉 copytree 会直接 FileExistsError
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=IGNORE)
        print(f"  {d}/")

    for f in INCLUDE_FILES:
        src = ROOT / f
        if not src.is_file():
            raise SystemExit(f"缺文件：{src}")
        shutil.copy2(src, PAYLOAD / f)
        print(f"  {f}")

    # 下载模型的脚本：安装时要用它拉权重，而且它只用标准库，
    # 所以哪怕依赖还没装完也能先跑。
    (PAYLOAD / "tools").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "tools" / "download_model.py", PAYLOAD / "tools")
    print("  tools/download_model.py")

    # 进度二传手：安装器用它替自己跑 pip，并把百分比写进状态文件。
    # 没有它，用户只能看着一个满格不动的进度条等十几分钟。
    # 和 download_model.py 一样住在 tools/ 里 —— 两个都是「装完还在用」
    # 的运行时脚本（用户也能手动跑），不属于构建期工具。
    shutil.copy2(ROOT / "tools" / "pip_progress.py", PAYLOAD / "tools")
    print("  tools/pip_progress.py")

    # 体检脚本：安装器先问它「这台机器上已经有什么」，据此整段跳过
    # 已经满足的步骤 —— 这是「增量安装」的全部依据。
    shutil.copy2(ROOT / "tools" / "check_env.py", PAYLOAD / "tools")
    print("  tools/check_env.py")

    # 进度窗口本体。它必须随包走，不能编译进什么 exe：
    #   · 用 PowerShell + WinForms 是因为 Windows 自带，零额外体积
    #   · 界面（暂停/取消/最小化）只有放在独立进程里才真的能动
    #     —— Inno 自己的窗口在 Pascal 代码执行期间不处理输入，见 iss 顶部注释
    # ⚠️ 这份是 UTF-8 **带 BOM** 的：Windows PowerShell 5.1 读不带 BOM 的
    #    UTF-8 脚本会把中文按 ANSI 解，界面上的字全是乱的。
    ps1 = ROOT / "tools" / "prep-ui.ps1"
    body = ps1.read_text(encoding="utf-8-sig")
    (PAYLOAD / "tools" / "prep-ui.ps1").write_text(body, encoding="utf-8-sig", newline="\r\n")
    print("  tools/prep-ui.ps1（UTF-8 BOM，PS 5.1 必需）")

    (PAYLOAD / "start.bat").write_text(LAUNCHER_BAT, encoding="utf-8", newline="\r\n")
    print("  start.bat（排查用，带控制台）")

    # 版本号塞进一个文件，Inno 和程序自己都能读
    (PAYLOAD / "VERSION.txt").write_text(
        f"AITeleprompter {INSTALLER_VERSION}\n"
        f"Python {PY_VERSION} embeddable\n"
        f"built {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )
    print("  VERSION.txt")


# --------------------------------------------------------------------------- #
# 3. 编译
# --------------------------------------------------------------------------- #
ISCC_CANDIDATES = (
    r"D:\Inno Setup 7\ISCC.exe",
    r"D:\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 7\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
)


def find_iscc(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise SystemExit(f"--iscc 指的文件不存在：{p}")
        return p
    for c in ISCC_CANDIDATES:
        if Path(c).is_file():
            return Path(c)
    raise SystemExit(
        "找不到 Inno Setup 的 ISCC.exe。\n"
        "  装一个：https://jrsoftware.org/isdl.php（免费）\n"
        "  或者用 --iscc 指到它的位置。"
    )


def compile_iss(iscc: Path) -> Path:
    iss = ROOT / "installer" / "AI提词器.iss"
    if not iss.is_file():
        raise SystemExit(f"缺安装脚本：{iss}")

    # ⛔ 版本号开关在 ISCC 7 里换名字了：老写法 /DName=value 现在会被当成
    #    「第二个脚本文件名」，报 "You may not specify more than one script
    #    filename" —— 而且它不会说 /D 不认识，非常误导。
    #    ISCC 7 = -dName=value（也可以写 --define=Name=value）
    #    为了兼容还在用 Inno 6 的机器，两种都试，后一种失败再退回老写法。
    attempts = (
        [iscc, f"-dMyAppVersion={INSTALLER_VERSION}", str(iss)],
        [iscc, f"/DMyAppVersion={INSTALLER_VERSION}", str(iss)],
    )
    last = None
    for cmd in attempts:
        try:
            run(cmd, cwd=ROOT / "installer")
            last = None
            break
        except SystemExit as e:                       # run() 失败会抛这个
            last = e
            print(f"  这样调用没成：{' '.join(cmd[1:2])} —— 换下一种写法重试")

    if last is not None:
        raise last

    out = DIST / f"AI提词器-{INSTALLER_VERSION}-安装程序.exe"
    if not out.is_file():
        raise SystemExit(f"编译似乎成功，但没找到产物：{out}")
    return out


# --------------------------------------------------------------------------- #
def smoke_project_import() -> None:
    """编译前最后一道闸：确认 payload 里的 python 能 import 同目录的模块。

    用户装完点不开程序的真因就是这一条不成立。装得上 ≠ 跑得起来，
    而这件事在安装日志里一点痕迹都没有（pip 九个包全部 OK），
    只有真正起一次进程才看得出来。

    探针是临时文件，跑完就删，不进安装包。
    """
    probe = PAYLOAD / "_import_probe.py"
    probe.write_text("OK = True\n", encoding="utf-8")
    try:
        out = run(
            [str(PAYLOAD / "python" / "python.exe"), "-c",
             "import _import_probe; print('probe-ok')"],
            cwd=PAYLOAD, capture=True,
        )
    finally:
        probe.unlink(missing_ok=True)
    if "probe-ok" not in out:
        raise SystemExit(
            "✗ payload 里的 python import 不到同目录模块。\n"
            f"  说明 python\\python{PY_TAG}._pth 少了 `..` 那一行 ——\n"
            "  这个包装到用户机器上会「装得上、点不开」，先修再编。"
        )
    print("  同目录 import 通过")


def main() -> int:
    global INSTALLER_VERSION

    ap = argparse.ArgumentParser(description="构建 AI 提词器 Windows 安装程序")
    ap.add_argument("-v", "--version", default="2.1.1", help="版本号，默认 2.1.1")
    ap.add_argument("--iscc", default=None, help="ISCC.exe 路径")
    ap.add_argument("--clean", action="store_true", help="构建前清空 build/")
    ap.add_argument("--skip-runtime", action="store_true",
                    help="复用已有的 build/payload/python（调试代码改动时省时间）")
    args = ap.parse_args()

    INSTALLER_VERSION = args.version

    print(f"AI 提词器 安装程序构建  ·  v{INSTALLER_VERSION}")
    print(f"项目：{ROOT}")

    if args.clean and BUILD.exists():
        shutil.rmtree(BUILD)
        print("已清空 build/")

    step("1/3 准备便携 Python 运行时")
    if args.skip_runtime and (PAYLOAD / "python" / "python.exe").is_file():
        print("  跳过（--skip-runtime，复用现有 python/）")
        # 复用也要核一遍 ._pth：旧 payload 可能是修这行之前生成的。
        # 不核的话，构建「成功」、安装「成功」，唯独程序点不开。
        write_pth(PAYLOAD / "python")
    else:
        prepare_runtime()

    step("2/3 拷贝项目代码")
    PAYLOAD.mkdir(parents=True, exist_ok=True)
    copy_project()

    step("3/3 编译安装程序")
    smoke_project_import()
    iscc = find_iscc(args.iscc)
    print(f"  编译器：{iscc}")
    setup = compile_iss(iscc)

    # ---- 汇总 ----
    py_size = sum(p.stat().st_size for p in (PAYLOAD / "python").rglob("*") if p.is_file())
    app_size = sum(p.stat().st_size for p in PAYLOAD.rglob("*")
                   if p.is_file() and (PAYLOAD / "python") not in p.parents)
    setup_size = setup.stat().st_size

    print("\n" + "=" * 62)
    print("构建完成")
    print("=" * 62)
    print(f"  便携运行时  {human(py_size):>10}   （Python {PY_VERSION} + pip）")
    print(f"  项目代码    {human(app_size):>10}")
    print(f"  安装包      {human(setup_size):>10}   {setup.relative_to(ROOT)}")
    print(f"  压缩比      {setup_size / max(py_size + app_size, 1) * 100:.1f}%")
    print()
    print("  注意：这个安装包不含 torch / transformers / 模型权重。")
    print("        用户安装时联网下载（CUDA 约 2.6 GB / CPU 约 240 MB，模型 1.8 GB）。")
    print()
    return 0


INSTALLER_VERSION = "2.1.1"

if __name__ == "__main__":
    sys.exit(main())
