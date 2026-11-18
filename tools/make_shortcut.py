"""在桌面创建「AI提词器」快捷方式。

    python tools/make_shortcut.py              # 建到当前用户桌面
    python tools/make_shortcut.py --remove     # 删掉它
    python tools/make_shortcut.py --all-users  # 建到公共桌面（所有用户可见，需管理员）

快捷方式指向 start.bat，工作目录设成本工程根目录，图标用 assets/teleprompter.ico。
换电脑 / 重装后跑一次即可重建，不用手动右键"发送到桌面"。

依赖 pywin32（只在建快捷方式时用，程序运行不需要）：
    pip install pywin32
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "start.bat"
ICON = ROOT / "assets" / "teleprompter.ico"
NAME = "AI提词器.lnk"


def _desktop(all_users: bool) -> Path:
    if all_users:
        return Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"
    return Path(os.environ["USERPROFILE"]) / "Desktop"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="创建/删除桌面快捷方式")
    ap.add_argument("--remove", action="store_true", help="删掉快捷方式")
    ap.add_argument("--all-users", action="store_true", help="建到公共桌面")
    args = ap.parse_args(argv)

    lnk = _desktop(args.all_users) / NAME

    if args.remove:
        if lnk.exists():
            lnk.unlink()
            print(f"[ok] 已删除 {lnk}")
        else:
            print(f"[--] 不存在：{lnk}")
        return 0

    if not TARGET.exists():
        print(f"[x] 找不到启动脚本：{TARGET}", file=sys.stderr)
        return 1

    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[x] 需要 pywin32：pip install pywin32", file=sys.stderr)
        print("    或者手动来：右键 start.bat → 发送到 → 桌面快捷方式", file=sys.stderr)
        return 2

    shell = win32com.client.Dispatch("WScript.Shell")
    sc = shell.CreateShortcut(str(lnk))
    sc.TargetPath = str(TARGET)
    sc.WorkingDirectory = str(ROOT)         # 不设的话 bat 里的相对路径会指到桌面
    sc.Description = "AI 语音跟随提词器（本地运行，不联网）"
    sc.WindowStyle = 1                      # 1=正常窗口；7=最小化
    if ICON.exists():
        sc.IconLocation = f"{ICON},0"
    sc.Save()

    print(f"[ok] {lnk}")
    print(f"     指向 {TARGET}")
    print(f"     图标 {ICON.name if ICON.exists() else '(默认)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
