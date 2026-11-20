"""磁盘占用统计与清理。

只做两件事：**看清楚谁在占地方**、**把能删的删掉**。

⛔ 永远不会碰 `data/scripts/`。那是用户写的稿子，是资产不是缓存 ——
这个模块里连一个「清理稿件」的函数都不该出现，免得哪天被人顺手调用。
删除只有两个入口：`clean_logs()` 和 `clean_install_cache()`。

为什么单独一个模块而不是写进 server.py：`run.py` 在**还没确认依赖装齐**的时候
就要用日志轮转（见 `_ensure_streams`），那时候 import fastapi / uvicorn 会直接炸。
本模块只依赖 os / pathlib / config，任何阶段都能安全 import。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import config

#: 单个日志文件的上限。超过就轮转成 `.log.1`，只留一份 —— 总占用上限约 1 MB。
#: 512 KB 够放几十次正常启动 + 好几个完整 traceback，真出事时够看。
MAX_LOG_BYTES = 512 * 1024

#: 安装过程中留下的中间物。`_tmp` 是下载缓存 + 进度文件（见 installer 的
#: `[Dirs]` 与 prep-ui.ps1 的 `--cache-dir`），装完之后就只剩占地方。
INSTALL_CACHE_DIR = config.ROOT / "_tmp"

#: 「程序本体」这一行要跳过哪些顶层目录。
#: 前两个是单独成行的数据与模型；后面几个**只在源码目录里存在**，安装到用户
#: 机器上根本没有 —— 不跳过的话，开发者看到的是「程序本体 1.3 GB」，
#: 那是他的 .venv 和 .git，不是程序。装了以后这两个分支给出的结果一样。
_NOT_PROGRAM = ("data", "models", ".git", ".venv", "venv", "dist", "build", "node_modules")


# ---------------------------------------------------------------- 日志
def log_paths() -> list[Path]:
    """所有日志文件（含轮转出来的 `.1`）。

    ⛔ 只认 `config.LOG_FILES` 这张表，**不用 `data/*.log` 通配**：通配迟早会把
    用户自己放进来的文件算成"日志"，然后被「清理」按钮删掉。
    """
    out: list[Path] = []
    for p in config.LOG_FILES:
        out.append(p)
        out.append(p.with_name(p.name + ".1"))
    return out


def rotate(path: Path, max_bytes: int = MAX_LOG_BYTES) -> Path | None:
    """超过上限就把 `x.log` 改名成 `x.log.1`（覆盖旧的）。返回轮转后的路径。

    ⛔ 顺序必须是「先 rename，再 open」。反过来的话，文件正被这个进程占着，
    Windows 上 rename 会 PermissionError，然后被调用方的 `except OSError` 吞掉 ——
    看起来"加了轮转但一点效果都没有"，最难查的那种。
    """
    try:
        if not path.is_file() or path.stat().st_size <= max_bytes:
            return None
    except OSError:
        return None
    dst = path.with_name(path.name + ".1")
    try:
        os.replace(path, dst)          # os.replace 在 Windows 上也能覆盖已存在的目标
        return dst
    except OSError:
        return None


def open_log(path: Path, max_bytes: int = MAX_LOG_BYTES):
    """轮转之后以「追加」方式打开日志，返回文件对象。

    追加而不是覆盖：已经有一个实例在跑时，再点一次快捷方式也会走到这里，
    用 "w" 会把正在跑的那个实例的启动记录抹掉，日志反而没用了。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate(path, max_bytes)
    return open(path, "a", encoding="utf-8", buffering=1)


# ---------------------------------------------------------------- 统计
def _tree_size(path: Path) -> tuple[int, int]:
    """递归数一个目录的 (字节, 文件数)。

    用 os.scandir 手写栈而不是 `rglob`：后者每个文件都要建一个 Path 对象，
    模型目录那种几万文件的地方会明显慢。快取数据在事件循环里跑，越省越好。

    数不出来的部分直接跳过（权限、文件刚被删）。**统计失败不该让面板报错** ——
    一个数字不准远好过整个设置页打不开。
    """
    total = 0
    files = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                            files += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, files


def _root_size_excluding(skip: tuple[str, ...]) -> tuple[int, int]:
    """安装目录的总大小，跳过 `skip` 里的顶层目录（它们要么单独成行，要么不算程序本体）。"""
    skip = tuple(s.lower() for s in skip)
    total = 0
    files = 0
    try:
        entries = list(os.scandir(config.ROOT))
    except OSError:
        return 0, 0
    for e in entries:
        if e.name.lower() in skip:
            continue
        try:
            if e.is_dir(follow_symlinks=False):
                b, f = _tree_size(Path(e.path))
                total += b
                files += f
            elif e.is_file(follow_symlinks=False):
                total += e.stat(follow_symlinks=False).st_size
                files += 1
        except OSError:
            continue
    return total, files


def scan() -> dict:
    """盘一遍谁在占地方。只统计、只显示，**不删任何东西**。

    四行固定 + 一行「安装缓存」（只在它真占地方时出现）。固定那四行加起来
    正好是整个程序的占用：稿件 ⊂ data，日志 ⊂ data，模型 ⊂ models，
    程序本体 = 安装目录减掉 data 与 models —— 所以 total 就是它们的和，
    不会重复计数。
    """
    rows: list[dict] = []

    # ① 稿件 —— 用户的资产，只报数，按钮都不给
    scripts_dir = config.SCRIPTS_DIR
    try:
        files = [p for p in scripts_dir.glob("*.md") if p.is_file()] if scripts_dir.is_dir() else []
    except OSError:
        files = []
    s_bytes = 0
    for p in files:
        try:
            s_bytes += p.stat().st_size
        except OSError:
            pass
    rows.append({"key": "scripts", "label": "稿件", "count": len(files), "unit": "篇",
                 "bytes": s_bytes, "cleanable": False,
                 "note": "你写的稿子，永远不自动删"})

    # ② 日志 —— 唯一会无限长的地方，也就是用户担心的那件事
    logs = []
    l_bytes = 0
    for p in log_paths():
        try:
            if p.is_file():
                logs.append(p)
                l_bytes += p.stat().st_size
        except OSError:
            pass
    rows.append({"key": "logs", "label": "日志", "count": len(logs), "unit": "个",
                 "bytes": l_bytes, "cleanable": True,
                 "note": "启动记录和报错栈，超过 512 KB 自动轮转"})

    # ③ 模型 —— 一次 1.8 GB，用户最想知道的大头
    models_dir = config.MODELS_DIR
    n_models = 0
    m_bytes = 0
    if models_dir.is_dir():
        try:
            with os.scandir(models_dir) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        n_models += 1
            m_bytes, _ = _tree_size(models_dir)
        except OSError:
            pass
    rows.append({"key": "models", "label": "语音模型", "count": n_models, "unit": "个",
                 "bytes": m_bytes, "cleanable": False,
                 "note": "识别用的权重，删了要重新下载"})

    # ④ 程序本体（安装目录去掉数据、模型和开发期才有的目录）
    # count 故意给 None：这里数出来的是"两千多个文件"，对用户没有任何可操作性，
    # 面板上显示"—"比显示一个吓人的数字好。真正要的是右边那个体积。
    p_bytes, _p_files = _root_size_excluding(_NOT_PROGRAM)
    rows.append({"key": "program", "label": "程序本体", "count": None, "unit": "",
                 "bytes": p_bytes, "cleanable": False,
                 "note": "程序、页面和自带的 Python 运行时"})

    # ⑤ 安装缓存 —— 装完就该没了；真在说明安装器的清理没跑成，或者被重装留下了
    if INSTALL_CACHE_DIR.is_dir():
        c_bytes, c_files = _tree_size(INSTALL_CACHE_DIR)
        if c_bytes:
            rows.append({"key": "install_cache", "label": "安装缓存", "count": c_files,
                         "unit": "个文件", "bytes": c_bytes, "cleanable": True,
                         "note": "安装时下载的包，装完就没用了"})

    return {
        "rows": rows,
        "total": sum(r["bytes"] for r in rows),
        "max_log_bytes": MAX_LOG_BYTES,
    }


# ---------------------------------------------------------------- 清理
def clean_logs() -> dict:
    """删掉日志文件。**只删 `log_paths()` 里的那几个，绝不碰 data/scripts/。**

    当前进程的 stdout 正挂在 `data/launch.log` 上（见 run.py 的 `_ensure_streams`），
    Windows 上删一个被打开的文件会 PermissionError。这时退一步把它**清空**：
    Python 的 "a" 模式带 O_APPEND，每次写都会先 seek 到末尾，所以清空之后
    日志从 0 字节重新长，不会留下一个巨大的空洞文件。

    返回 `{"deleted": [...], "truncated": [...], "failed": [...]}` —— 说清楚每个
    文件到底怎么了，别让用户点了按钮看到"成功"却发现文件还在。
    """
    out: dict = {"deleted": [], "truncated": [], "failed": []}
    for p in log_paths():
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        try:
            p.unlink()
            out["deleted"].append(p.name)
            continue
        except OSError:
            pass
        try:
            with open(p, "w", encoding="utf-8"):
                pass
            out["truncated"].append(p.name)
        except OSError as e:
            out["failed"].append(f"{p.name}：{e}")
    return out


def clean_install_cache() -> dict:
    """删掉安装缓存目录（`_tmp`）。删不掉就算了，不能因此报错或崩掉。"""
    out: dict = {"deleted": [], "truncated": [], "failed": []}
    if not INSTALL_CACHE_DIR.is_dir():
        return out
    try:
        shutil.rmtree(INSTALL_CACHE_DIR)
        out["deleted"].append(INSTALL_CACHE_DIR.name + "/")
    except OSError as e:
        out["failed"].append(f"{INSTALL_CACHE_DIR.name}/：{e}")
    return out


def sweep_startup_junk() -> list[str]:
    """启动时顺手扫一遍安装器留下的垃圾。

    只扫**明确是垃圾**的东西：
      · 安装目录根上的 `is-*.tmp`（Inno 自己的临时文件，实测见过残留 4.4 MB）
      · `_tmp/` 里的四个进度/标志文件（progress.txt / cancel.flag / pause.flag /
        prep-result.txt）—— 它们只在安装过程中有意义

    ⛔ **不删 `_tmp/pipcache`**。那是 pip 下载缓存（torch 一个包就 240 MB），
    留着只为一件事：用户"重新运行安装程序补依赖"时不用重下 240 MB。
    要回收它请走设置页的「数据占用」面板 —— 那是用户自己做的决定，不是程序替他做。

    清不掉就算了：安装目录只读、文件被占用都可能发生，**绝不能因此起不来**。
    """
    gone: list[str] = []
    try:
        for p in config.ROOT.glob("is-*.tmp"):
            try:
                if p.is_file():
                    p.unlink()
                    gone.append(p.name)
            except OSError:
                continue
    except OSError:
        pass

    for name in ("progress.txt", "cancel.flag", "pause.flag", "prep-result.txt"):
        try:
            p = INSTALL_CACHE_DIR / name
            if p.is_file():
                p.unlink()
                gone.append(f"_tmp/{name}")
        except OSError:
            continue

    # 空目录顺手收掉（非空时 rmdir 会失败，正好保住 pipcache）
    try:
        INSTALL_CACHE_DIR.rmdir()
        gone.append("_tmp/")
    except OSError:
        pass
    return gone


# ---------------------------------------------------------------- 清理入口表
#: HTTP 接口只认这几个名字。⛔ 这张表里永远不该出现「稿件」——
#: 前端就算传了 `what=scripts` 也只会拿到 400。
CLEANERS = {
    "logs": clean_logs,
    "install_cache": clean_install_cache,
}
