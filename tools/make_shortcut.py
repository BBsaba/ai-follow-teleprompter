"""在桌面创建 / 查看 / 删除「AI提词器」快捷方式。

    python tools/make_shortcut.py               # 建到当前用户桌面（无控制台窗口）
    python tools/make_shortcut.py --with-console # 带控制台，能看见报错，开发时用
    python tools/make_shortcut.py --show        # 打印现有快捷方式指向哪
    python tools/make_shortcut.py --remove      # 删掉它
    python tools/make_shortcut.py --all-users   # 建到公共桌面（所有用户可见，需管理员）

默认指向 **pythonw.exe + run.py**，双击不弹黑框。这条路是 v2.2.1 才通的：
在那之前 pythonw 下 sys.stdout 是 None，uvicorn 初始化的第一步就会抛异常，
表现成"双击没反应"（见开发文档 §18.14）。现在 run.py 会自己把
stdout/stderr 接到 data\\launch.log，所以关掉控制台也不会变成哑巴。

⚠️ 这个脚本**不需要 pywin32**。它用 ctypes 直接调 Windows 的 IShellLinkW
（和资源管理器建快捷方式走的是同一套 API），比 win32com 少一个 10 MB 的依赖。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from win_shortcut import create_shortcut, read_shortcut  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NAME = "AI提词器.lnk"
ICON = ROOT / "assets" / "teleprompter.ico"
START_BAT = ROOT / "start.bat"


def _desktop(all_users: bool) -> Path:
    if all_users:
        return Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"
    return Path(os.environ["USERPROFILE"]) / "Desktop"


def _find_pythonw() -> Path | None:
    """按 start.bat 同样的优先顺序找解释器，然后取它的 pythonw。

    顺序：.venv\\Scripts → %TELEPROMPTER_PYTHON% → 当前解释器 → PATH
    """
    cands: list[Path] = []

    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        cands.append(venv_py)

    pinned = os.environ.get("TELEPROMPTER_PYTHON")
    if pinned:
        cands.append(Path(pinned))

    if sys.executable:
        cands.append(Path(sys.executable))

    import shutil

    for name in ("python.exe",):
        found = shutil.which(name)
        if found:
            cands.append(Path(found))

    for py in cands:
        # python.exe 旁边通常就有 pythonw.exe（venv 和官方安装包都有）
        pw = py.with_name("pythonw.exe")
        if pw.exists():
            return pw
    return None


def build(all_users: bool, with_console: bool) -> int:
    lnk = _desktop(all_users) / NAME
    desc = "AI 语音跟随提词器（本地运行，不联网）"

    if with_console:
        if not START_BAT.exists():
            print(f"[x] 找不到 {START_BAT}", file=sys.stderr)
            return 1
        create_shortcut(
            str(lnk),
            target=str(START_BAT),
            working_dir=str(ROOT),
            description=desc,
            icon=str(ICON) if ICON.exists() else "",
            show_cmd=1,
        )
        print(f"[ok] {lnk}")
        print(f"     指向 {START_BAT.name}（带控制台窗口）")
        return 0

    pythonw = _find_pythonw()
    if pythonw is None:
        print("[!] 没找到 pythonw.exe，退回 start.bat（会出现控制台窗口）", file=sys.stderr)
        return build(all_users, with_console=True)

    create_shortcut(
        str(lnk),
        target=str(pythonw),
        # 路径里有空格也不怕，统一加引号
        arguments=f'"{ROOT / "run.py"}"',
        working_dir=str(ROOT),
        description=desc,
        icon=str(ICON) if ICON.exists() else "",
        show_cmd=1,
    )
    print(f"[ok] {lnk}")
    print(f"     指向 {pythonw}")
    print(f"     参数 \"{ROOT / 'run.py'}\"")
    print("     无控制台窗口；输出见 data\\launch.log")
    return 0


def show(all_users: bool) -> int:
    lnk = _desktop(all_users) / NAME
    if not lnk.exists():
        print(f"[--] 不存在：{lnk}")
        return 1
    print(f"{lnk}  ({lnk.stat().st_size} 字节)")
    for k, v in read_shortcut(str(lnk)).items():
        print(f"  {k:<12} = {v}")
    return 0


def remove(all_users: bool) -> int:
    lnk = _desktop(all_users) / NAME
    if lnk.exists():
        lnk.unlink()
        print(f"[ok] 已删除 {lnk}")
    else:
        print(f"[--] 不存在：{lnk}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="创建/查看/删除桌面快捷方式")
    ap.add_argument("--remove", action="store_true", help="删掉快捷方式")
    ap.add_argument("--show", action="store_true", help="打印现有快捷方式的字段")
    ap.add_argument("--all-users", action="store_true", help="公共桌面（所有用户可见）")
    ap.add_argument(
        "--with-console",
        action="store_true",
        help="指向 start.bat，保留控制台窗口（开发时看报错用）",
    )
    args = ap.parse_args(argv)

    if args.remove:
        return remove(args.all_users)
    if args.show:
        return show(args.all_users)
    return build(args.all_users, args.with_console)


if __name__ == "__main__":
    raise SystemExit(main())
