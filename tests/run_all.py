"""一条命令跑完全部测试。

    python tests/run_all.py            # 能跑的全跑
    python tests/run_all.py --fast     # 只跑不需要服务/模型的（script + align）

为什么不用 pytest：
    这些测试是**脚本式**的——自己维护 OK/FAIL 计数，靠 `check()` 断言，
    最后打印「通过 N，失败 M」。pytest 会按 test_* 名字把它们收集成空壳
    （函数体只调 check，没有 assert），跑完报「14 passed」，是**假绿**。
    所以 tests/conftest.py 里显式禁止 pytest 收集，唯一入口就是本文件。

依赖与前置（缺了会跳过并说明，不算失败）：
    test_live / test_follow_e2e  → 需要 models/ 里的权重，首次加载 10-20 秒
    test_ws / test_ui            → 需要服务已在 127.0.0.1:8756 运行
    test_ui                      → 需要 playwright（pip install playwright && playwright install chromium）
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable

# 子进程强制 UTF-8。测试脚本会 print 中文，而英文 Windows 的默认 stdout 编码是
# cp1252，一打中文就 UnicodeEncodeError——GitHub Actions 的 windows runner 正是
# 这种情况，实测 5 个文件全红。run_all 自己的 reconfigure 管不到子进程，
# 所以必须在这里显式传下去。
_CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

# 回环绝不该走代理：本机常全局设 HTTP_PROXY，会让 websocket 连 127.0.0.1 也 502
os.environ["NO_PROXY"] = "127.0.0.1,localhost," + os.environ.get("NO_PROXY", "")
os.environ["no_proxy"] = os.environ["NO_PROXY"]

BASE = "http://127.0.0.1:8756"

# (脚本, 是否需要服务, 是否需要模型)
STEPS = [
    ("test_script.py", False, False),
    ("test_align.py", False, False),
    ("test_server.py", False, False),
    ("test_model_finder.py", False, False),
    ("test_settings.py", False, False),
    ("test_storage.py", False, False),
    ("test_follow_e2e.py", False, True),
    ("test_live.py", False, True),
    ("test_ws.py", True, False),
    ("test_ui.py", True, False),
]

SUM_RE = re.compile(r"通过\s*(\d+)\s*[，,]\s*失败\s*(\d+)")


def _service_up() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/api/state", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _model_present() -> bool:
    return (ROOT / "models" / "Qwen3-ASR-0.6B" / "model.safetensors").exists()


def _playwright_ok() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 用户数据保护
# ⛔ 为什么必须有这一段（v2.3.0 事故）：
#   test_ws / test_ui 是**通过 HTTP 连真实服务**测的，服务读写的就是项目里的
#   `data/`。跑一遍 test_ui，它会拖滑块、存稿 → 用户的 `per_line`、`cps`、字号
#   全被改成测试用例里的值，`001.md` 的 mtime 也被刷新。
#   实测代价：用户手工调的「每行 20 字」被改回 14，还以为是程序自己丢的设置。
#   → 连服务的测试跑之前先把 data/ 整个拷走，跑完再放回来。

def _backup_user_data() -> Path | None:
    import shutil
    import tempfile

    data = ROOT / "data"
    if not data.is_dir():
        return None
    tmp = Path(tempfile.mkdtemp(prefix="aitp-test-backup-"))
    try:
        shutil.copytree(data, tmp / "data")
        return tmp
    except OSError as e:
        print(f"  ⚠️ 备份 data/ 失败（{e}）—— 本次跑测试可能改动你的设置")
        shutil.rmtree(tmp, ignore_errors=True)
        return None


def _restore_user_data(tmp: Path | None) -> None:
    import shutil

    if tmp is None:
        return
    src, data = tmp / "data", ROOT / "data"
    if not src.is_dir():
        return
    try:
        for name in ("state.json",):        # 设置
            s = src / name
            if s.exists():
                shutil.copy2(s, data / name)
        ss, ds = src / "scripts", data / "scripts"   # 稿件
        if ss.is_dir():
            if ds.is_dir():
                shutil.rmtree(ds)
            shutil.copytree(ss, ds)
        print("  （已把你跑测试前的 data/ 放回去：设置和稿件都是原样）")
    except OSError as e:
        print(f"  ⚠️ 还原 data/ 失败：{e}")
        print(f"     手动恢复：把 {tmp / 'data'} 里的内容拷回 {data}")
        return
    shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="跑 AITeleprompter 全部测试")
    ap.add_argument("--fast", action="store_true", help="只跑不需要服务和模型的")
    args = ap.parse_args(argv)

    try:  # Windows 控制台可能是 GBK，测试输出里有中文和箭头
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    have_svc = _service_up()
    have_model = _model_present()
    have_pw = _playwright_ok()

    total_ok = total_bad = 0
    ran, skipped, failed_files = [], [], []

    backup = _backup_user_data() if have_svc else None

    for name, need_svc, need_model in STEPS:
        if args.fast and (need_svc or need_model):
            skipped.append((name, "fast 模式"))
            continue
        if need_model and not have_model:
            skipped.append((name, "缺 models/Qwen3-ASR-0.6B"))
            continue
        if need_svc and not have_svc:
            skipped.append((name, "服务未在 " + BASE + " 运行"))
            continue
        if name == "test_ui.py" and not have_pw:
            skipped.append((name, "未安装 playwright"))
            continue

        print(f"\n{'=' * 60}\n  {name}\n{'=' * 60}", flush=True)
        r = subprocess.run([PY, str(HERE / name)], cwd=str(ROOT),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=_CHILD_ENV)
        out = (r.stdout or "") + (r.stderr or "")
        # 只回显失败的断言行，通过的太吵
        for line in out.splitlines():
            if "FAIL" in line or "✗" in line:
                print("  " + line.strip())
        m = None
        for m in SUM_RE.finditer(out):
            pass
        if m:
            ok, bad = int(m.group(1)), int(m.group(2))
            total_ok += ok
            total_bad += bad
            print(f"  → {ok} 通过 / {bad} 失败", flush=True)
            ran.append(name)
            if bad:
                failed_files.append(name)
        else:
            total_bad += 1
            failed_files.append(name)
            print(f"  → 没跑到汇总行，退出码 {r.returncode}，末尾输出：")
            for line in out.strip().splitlines()[-6:]:
                print("     " + line)

    _restore_user_data(backup)

    print("\n" + "-" * 60)
    print(f"合计：{total_ok} 通过 / {total_bad} 失败   （{len(ran)} 个文件）")
    if skipped:
        print("跳过：")
        for name, why in skipped:
            print(f"  - {name}：{why}")
    if failed_files:
        print("失败文件：" + "、".join(failed_files))
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
