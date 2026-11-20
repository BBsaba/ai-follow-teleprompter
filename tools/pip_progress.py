#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""替安装器跑 pip，把实时进度写进状态文件。

为什么需要这个中间人
--------------------
Inno Setup 的 Exec 只能拿到子进程的退出码，**读不到它的 stdout**；
而 pip 的进度条一旦被重定向（不是真终端）就退化 —— 实测只会输出
下载完成后的那一行，中途一个字节都不刷。于是用户面对的就是
「进度条满格不动十几分钟」，分不清是在下载还是已经死了。

所以让这个脚本当二传手：
  1. 它 Popen 起 pip，把子进程的 TEMP 指到安装目录下（不占 C 盘）
  2. 每 0.5 秒量一次下载目录的字节数，算出百分比
  3. 把「阶段|百分比|文字」写进状态文件
  4. Inno 那边轮询这个文件，刷新进度条和状态栏

状态文件格式（一行，竖线分隔，Pascal 侧自己切三段）
--------------------------------------------------------
    STAGE|pct|文字

    STAGE ∈ LOOKUP / DOWNLOAD / INSTALL / DONE / FAIL

tools/download_model.py 里的 Status 类写的是同一个格式，
改格式要两边一起改，否则安装器会有一半阶段读不出来。

为什么还要单独抓 wheel 链接
--------------------------
`pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cu126`
在实测里解析索引用掉 **5 分钟**（pip 要把整个索引页里几千个 wheel 逐个比对
版本和平台标签）。直接给 wheel 的完整 URL，pip 就跳过这一步。
所以这里先用 urllib 抓一次索引页、正则挑出匹配的那个链接。

用法（由 .iss 调用，用户不会直接跑）
----------------------------------
    python tools/pip_progress.py --mode torch --status S --log L --tmp T \\
        --lo 28 --hi 76 --version 2.14.0 --index URL --py-tag cp313

    python tools/pip_progress.py --mode pip --status S --log L --tmp T \\
        --lo 76 --hi 96 -- -r requirements.txt --index-url MIRROR
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

#: 下载阶段最多占多少时间用于"等索引"——超过就认为抓不到链接，退回 pip 自己解析
LOOKUP_TIMEOUT = 60

#: 用户点「取消」时，安装器会创建这个文件；我们看见就收手。
#: 为什么用文件而不杀进程：Inno 的 Exec 不返回子进程 PID，安装器手上没有
#: 句柄可杀；而且 taskkill 按镜像名杀会误伤用户自己开的 python。
CANCEL_FILE: Path | None = None

#: 用户点「暂停」时同理。区别是暂停要留着半截文件，取消也留着 ——
#: 下次接着下，不然 2.6 GB 白费。
PAUSE_FILE: Path | None = None

#: 退出码约定（和 installer\prep-ui.ps1 对齐，改要一起改）
RC_OK = 0
RC_FAIL = 1
RC_CANCEL = 3
RC_PAUSE = 4


class _Cancelled(Exception):
    """用户取消了安装 —— 这不是失败，别当错误去重试。"""


class _Paused(Exception):
    """用户按了暂停 —— 也不是失败，进度窗口会等他说「继续」再叫我们一次。"""


def cancelled() -> bool:
    return CANCEL_FILE is not None and CANCEL_FILE.exists()


def paused() -> bool:
    return PAUSE_FILE is not None and PAUSE_FILE.exists()


# --------------------------------------------------------------------------- #
# 状态文件
# --------------------------------------------------------------------------- #
class Status:
    def __init__(self, path: Path, lo: int, hi: int) -> None:
        self.path = path
        self.lo = lo
        self.hi = hi
        self.last = 0.0
        self.t0 = time.time()

    def write(self, stage: str, pct: float, text: str, force: bool = False) -> None:
        """pct 用 0–100 的相对值，这里映射到 [lo, hi]。"""
        now = time.time()
        if not force and now - self.last < 0.25:
            return
        self.last = now
        real = self.lo + (self.hi - self.lo) * max(0.0, min(100.0, pct)) / 100.0
        line = f"{stage}|{real:.0f}|{text}".replace("\n", " ").replace("\r", " ")
        try:
            # 先写临时文件再替换，避免 Inno 读到半行
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(line[:400], encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass


def elapsed(t0: float) -> str:
    s = int(time.time() - t0)
    return f"{s // 60}:{s % 60:02d}"


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def dir_size(p: Path) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(p):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


# --------------------------------------------------------------------------- #
# 找 wheel 链接
# --------------------------------------------------------------------------- #
def find_wheel(index_url: str, version: str, py_tag: str) -> str | None:
    """从 pytorch 的索引页里挑出 cp313-win_amd64 那个 wheel 的绝对地址。

    索引页形如：
        <a href="../../whl/cu126/torch-2.14.0%2Bcu126-cp313-cp313-win_amd64.whl#sha256=...">
    版本号里的 + 是 URL 编码的 %2B，所以匹配时两种写法都要认。
    """
    page = index_url.rstrip("/") + "/torch/"
    try:
        with urllib.request.urlopen(page, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception:
        return None

    ver = re.escape(version)
    # 只认本机平台：win_amd64 + 对应 cpython tag
    pat = re.compile(
        r'href="([^"#]*?torch-' + ver + r'(?:%2B|\+)cu\d+-' + py_tag + r'-' + py_tag +
        r'-win_amd64\.whl)(?:#[^"]*)?"',
        re.IGNORECASE,
    )
    m = pat.search(html)
    if not m:
        return None

    href = m.group(1)
    if href.startswith("http"):
        return href
    # 相对地址，按 index 页的目录拼回去
    from urllib.parse import urljoin
    return urljoin(page, href)


# --------------------------------------------------------------------------- #
# 自己下载 wheel（进度最准）
# --------------------------------------------------------------------------- #
def download_with_progress(url: str, dest: Path, status: Status, label: str) -> int:
    """把 wheel 下到 dest，边下边报进度。返回 RC_* 退出码。

    为什么不交给 pip 下：pip 只在真终端里才刷进度条，一旦输出被重定向就
    退化成"下完才写一行"；而且它的临时文件落在系统 TEMP（C 盘），
    2.6 GB 对 C 盘紧张的人不友好。自己下能做到：
      · 总大小来自 Content-Length，百分比是准的
      · 下到安装目录里，不占 C 盘
      · 进度、速度、剩余秒数都能算
      · 断点续传：取消 / 暂停 / 断网之后，下一次从断点接着下

    断点续传的两个坑
    ----------------
    1. 服务器可能不支持 Range（返回 200 而不是 206）。那时不能接着写，
       必须截断重来 —— 否则文件会变成「新内容接在旧内容后面」的垃圾。
    2. 上次下的可能是**另一个版本**的 wheel。旁边留一份 .url 记录当时的
       地址，地址变了就把旧文件丢掉，不然会拼出一个大小看着对、
       解压时报 CRC 错的包，极难查。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = dest.with_suffix(".url")

    have = dest.stat().st_size if dest.exists() else 0
    if have:
        try:
            if meta.read_text(encoding="utf-8").strip() != url:
                dest.unlink()
                have = 0
        except OSError:
            try:
                dest.unlink()
            except OSError:
                pass
            have = 0
    try:
        meta.write_text(url, encoding="utf-8")
    except OSError:
        pass

    headers = {"User-Agent": "AITeleprompter-installer"}
    if have:
        headers["Range"] = f"bytes={have}-"

    t0 = time.time()
    got = have
    last = 0.0
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:
            # 「范围不可满足」= 文件其实已经完整了
            status.write("DOWNLOAD", 100, f"{label}  已下载完成", force=True)
            return RC_OK
        status.write("FAIL", 0, f"{label}  下载失败：{e}", force=True)
        return RC_FAIL
    except Exception as e:                       # noqa: BLE001
        status.write("FAIL", 0, f"{label}  下载失败：{e}", force=True)
        return RC_FAIL

    try:
        with r:
            if have and getattr(r, "status", 200) == 206:
                mode = "ab"
                total = have + int(r.headers.get("Content-Length") or 0)
                status.write("DOWNLOAD", got * 100.0 / total if total else 0,
                             f"{label}  接着上次的 {human(have)} 继续…", force=True)
            else:
                have = 0
                got = 0
                mode = "wb"
                total = int(r.headers.get("Content-Length") or 0)

            with open(dest, mode) as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    now = time.time()
                    if now - last >= 0.3:
                        last = now
                        if cancelled():          # 0.3 秒查一次，够快也不费事
                            status.write("FAIL", 0,
                                         f"{label}  已取消（已下的 {human(got)} 留着，下次接着下）",
                                         force=True)
                            return RC_CANCEL
                        if paused():
                            pct = min(99.0, got * 100.0 / total) if total else 0.0
                            status.write("PAUSED", pct,
                                         f"{label}  已暂停在 {human(got)}", force=True)
                            return RC_PAUSE
                        speed = (got - have) / max(now - t0, 0.01)
                        if total:
                            pct = min(99.0, got * 100.0 / total)
                            eta = int((total - got) / max(speed, 1))
                            text = (f"{label}  {human(got)} / {human(total)}  "
                                    f"{human(speed)}/s  剩 {eta // 60}:{eta % 60:02d}")
                        else:
                            pct = 0.0
                            text = f"{label}  {human(got)}  {human(speed)}/s"
                        status.write("DOWNLOAD", pct, text)

            size = dest.stat().st_size
            if total and size != total:
                status.write("FAIL", 0, f"{label}  下载不完整（{human(size)} / {human(total)}）",
                             force=True)
                return RC_FAIL
            status.write("DOWNLOAD", 100, f"{label}  已下载 {human(got)}", force=True)
            return RC_OK
    except Exception as e:                       # noqa: BLE001
        status.write("FAIL", 0, f"{label}  下载中断：{e}（已下的部分留着，下次接着下）",
                     force=True)
        return RC_FAIL


# --------------------------------------------------------------------------- #
# 跑 pip 并盯进度
# --------------------------------------------------------------------------- #
def run_pip(python: str, args: list[str], tmp: Path, log_path: Path,
            status: Status, label: str, expect_bytes: int = 0) -> int:
    env = os.environ.copy()
    env.update({
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "PYTHONUNBUFFERED": "1",        # 让 pip 的输出别攒在缓冲区里
        "PYTHONIOENCODING": "utf-8",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    })

    log = open(log_path, "a", encoding="utf-8", errors="replace")
    log.write(f"\n--- {label} ---\n")
    log.write("$ " + " ".join(args) + "\n")
    log.flush()

    t0 = time.time()
    proc = subprocess.Popen(
        [python, "-m", "pip", "install"] + args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, bufsize=0,
    )

    # 边读输出边记日志：既保留 pip 的原始记录，又从中捞总大小
    total_bytes = expect_bytes
    buf = b""
    last_size = 0
    last_t = time.time()
    speed = 0.0

    def pump() -> bool:
        """读一块输出写日志，顺手抓 'Downloading xxx (2.6 GB)'。返回进程是否还活着。"""
        nonlocal buf, total_bytes
        chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096)
        if not chunk:
            return False
        buf += chunk
        while b"\r" in buf or b"\n" in buf:
            idx_r = buf.find(b"\r")
            idx_n = buf.find(b"\n")
            if idx_r < 0:
                idx = idx_n
            elif idx_n < 0:
                idx = idx_r
            else:
                idx = min(idx_r, idx_n)
            line = buf[:idx].decode("utf-8", "replace").strip()
            buf = buf[idx + 1:]
            if not line:
                continue
            log.write(line + "\n")
            log.flush()
            m = re.search(r"\((\d+(?:\.\d+)?)\s*(kB|MB|GB)\)", line)
            if m and "Downloading" in line:
                num, unit = float(m.group(1)), m.group(2)
                total_bytes = int(num * {"kB": 1 << 10, "MB": 1 << 20, "GB": 1 << 30}[unit])
        return True

    killed_for_cancel = False
    while proc.poll() is None:
        if cancelled():
            # pip 自己不会看我们的暗号，只能直接终止它。
            # 用 kill 不用 terminate：Windows 上 terminate 只是 WM_CLOSE，
            # 控制台程序经常收不到。
            proc.kill()
            killed_for_cancel = True
            break
        try:
            if not pump():
                break
        except Exception:
            break
        # 量下载目录
        cur = dir_size(tmp)
        now = time.time()
        dt = now - last_t
        if dt >= 0.4:
            inst = (cur - last_size) / dt
            speed = inst if inst > 0 else speed * 0.6
            last_size, last_t = cur, now
        if total_bytes > 0:
            pct = min(99.0, cur * 100.0 / total_bytes)
            status.write("DOWNLOAD", pct,
                         f"{label}  {human(cur)} / {human(total_bytes)}  "
                         f"{human(max(speed, 0))}/s  {elapsed(t0)}")
        else:
            # 还没拿到总大小（在解析索引），只能报已下载量
            status.write("LOOKUP", 0,
                         f"{label}  已接收 {human(cur)}  {elapsed(t0)}  "
                         f"（正在解析版本索引，这一步可能要几分钟）")

    # 收尾：把剩余输出读完
    try:
        while pump():
            pass
    except Exception:
        pass

    rc = proc.wait()
    log.close()
    if killed_for_cancel:
        # 退出码要能区分「用户要走」和「装失败」——
        # 进度窗口按这个决定是收工还是报错重试
        return RC_CANCEL
    return rc


def _write_final(status: Status, rc: int, label: str) -> None:
    """收尾状态。取消和失败必须分开写 —— 进度窗口靠这个给人不同的话：
    取消是「已停止，下次接着来」，失败是「出问题了」。"""
    if rc == RC_OK:
        status.write("DONE", 100, f"{label}  完成", force=True)
    elif rc == RC_CANCEL:
        status.write("FAIL", 0, f"{label}  已取消", force=True)
    else:
        status.write("FAIL", 0, f"{label}  失败（退出码 {rc}）", force=True)


# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    global CANCEL_FILE, PAUSE_FILE

    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["torch", "pip"], required=True)
    ap.add_argument("--status", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--tmp", required=True)
    ap.add_argument("--label", default="正在下载")
    ap.add_argument("--lo", type=int, default=0)
    ap.add_argument("--hi", type=int, default=100)
    ap.add_argument("--version", default="")
    ap.add_argument("--index", default="")
    ap.add_argument("--py-tag", default="cp313")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--cancel", default=None, help="取消标记文件（安装程序用）")
    ap.add_argument("--pause", default=None, help="暂停标记文件（安装程序用）")
    ap.add_argument("rest", nargs=argparse.REMAINDER)

    a = ap.parse_args(argv)
    CANCEL_FILE = Path(a.cancel) if a.cancel else None
    PAUSE_FILE = Path(a.pause) if a.pause else None

    status = Status(Path(a.status), a.lo, a.hi)
    tmp = Path(a.tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    log_path = Path(a.log)

    rest = a.rest
    if rest and rest[0] == "--":
        rest = rest[1:]

    # ---- 1. torch 模式：自己下 wheel，进度才准 ----
    if a.mode == "torch":
        status.write("LOOKUP", 0, f"{a.label}  正在查询版本信息…", force=True)
        url = find_wheel(a.index, a.version, a.py_tag) if a.index else None

        if url:
            # 下载占这一段进度的 92%，剩下的留给解压安装
            split = a.lo + int((a.hi - a.lo) * 0.92)
            wheel = tmp / "torch-download.whl"

            status.lo, status.hi = a.lo, split
            rc = download_with_progress(url, wheel, status, a.label)
            if rc != RC_OK:
                # 取消 / 暂停 / 断网：**半截 wheel 和 .url 都留着**。
                # 上一版在这里删了文件，用户下次还得从 0 开始下 2.6 GB，
                # 这是最招人烦的一点。
                return rc

            status.lo, status.hi = split, a.hi
            status.write("INSTALL", 40, "正在解压安装 PyTorch（约 4 GB，要几分钟）…", force=True)
            rc = run_pip(sys.executable,
                         [str(wheel), "--no-deps", "--disable-pip-version-check",
                          "--no-warn-script-location"],
                         tmp, log_path, status, "解压安装 PyTorch")
            if rc == RC_OK:
                # 只有装成功了才删 —— 装失败要留着下次再来，省一次 2.6 GB
                try:
                    wheel.unlink()
                    wheel.with_suffix(".url").unlink()
                except OSError:
                    pass
                status.write("DONE", 100, f"{a.label}  完成", force=True)
            elif rc == RC_CANCEL:
                status.write("FAIL", 0, f"{a.label}  已取消", force=True)
            else:
                status.write("FAIL", 0, f"{a.label}  安装失败（退出码 {rc}）", force=True)
            return rc

        # 抓不到链接就退回 pip 自己解析（慢，可能好几分钟，但能装）
        status.write("LOOKUP", 0,
                     f"{a.label}  没抓到直链，改用 pip 解析索引（较慢）…", force=True)
        pip_args = [f"torch=={a.version}", "--index-url", a.index,
                    "--disable-pip-version-check", "--no-warn-script-location"]
        if a.no_cache:
            pip_args.append("--no-cache-dir")
        rc = run_pip(sys.executable, pip_args, tmp, log_path, status, a.label)
        _write_final(status, rc, a.label)
        return rc

    # ---- 2. pip 模式：requirements.txt 之类，包小、包多，交给 pip ----
    rc = run_pip(sys.executable, rest, tmp, log_path, status, a.label)
    _write_final(status, rc, a.label)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
