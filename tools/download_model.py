"""下载 Qwen3-ASR 权重到 models/ 目录。

为什么自己写而不用 modelscope.snapshot_download：
  · 不想为一次下载引入 modelscope + datasets 一整套依赖；
  · 断点续传、失败重试、进度显示都只要几十行；
  · 别人拿去开源仓库里跑，**只用标准库**，不装任何东西就能下。

用法：
    python tools/download_model.py                # 默认 0.6B
    python tools/download_model.py --model 1.7B
    python tools/download_model.py --check        # 只检查完整性，不下载
    python tools/download_model.py --dir D:\\models\\asr

⚠️ 本脚本用的是 **ModelScope 的文件列表 API**，只支持 ModelScope 及其兼容镜像。
   从 HuggingFace 下载请走 `hf download` 或浏览器手动下载，脚本里会给出提示。
   下载位置不用改代码：程序会在 models/ 里按内容自动找（见 app/model_finder.py）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")

REPOS = {
    "0.6B": "Qwen/Qwen3-ASR-0.6B",
    "1.7B": "Qwen/Qwen3-ASR-1.7B",
}

# 模型体积大但不该进的目录
SKIP_PREFIX = (".git",)

CHUNK = 1 << 20  # 1 MiB


def _opener() -> urllib.request.OpenerDirector:
    # 绕开系统代理：很多机器上 pip/curl 能通、urllib 走代理反而不通
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def list_files(repo: str, endpoint: str) -> list[tuple[str, int]]:
    url = f"{endpoint}/api/v1/models/{repo}/repo/files?Revision=master&Recursive=true"
    with _opener().open(url, timeout=30) as r:
        data = json.load(r)
    out = []
    for f in data.get("Data", {}).get("Files", []):
        path = f.get("Path", "")
        if not path or path.startswith(SKIP_PREFIX) or path.endswith("/"):
            continue
        out.append((path, int(f.get("Size") or 0)))
    return out


def resolve_url(repo: str, path: str, endpoint: str) -> str:
    return f"{endpoint}/models/{repo}/resolve/master/{path}"


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def fetch(repo: str, path: str, dest: str, endpoint: str, tries: int = 5) -> None:
    url = resolve_url(repo, path, endpoint)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(1, tries + 1):
        have = os.path.getsize(dest) if os.path.exists(dest) else 0
        req = urllib.request.Request(url)
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            with _opener().open(req, timeout=60) as r:
                total = have + int(r.headers.get("Content-Length") or 0)
                mode = "ab" if have and r.status == 206 else "wb"
                if mode == "wb":
                    have = 0
                t0 = time.time()
                with open(dest, mode) as fh:
                    done = have
                    while True:
                        block = r.read(CHUNK)
                        if not block:
                            break
                        fh.write(block)
                        done += len(block)
                        if total:
                            pct = done * 100 / total
                            sp = (done - have) / max(1e-6, time.time() - t0)
                            sys.stdout.write(
                                f"\r  {path:32s} {pct:5.1f}%  "
                                f"{human(done)}/{human(total)}  {human(sp)}/s   "
                            )
                            sys.stdout.flush()
            if total and os.path.getsize(dest) != total:
                raise IOError(f"大小不符 {os.path.getsize(dest)} != {total}")
            sys.stdout.write("\n")
            return
        except (urllib.error.URLError, IOError, TimeoutError) as e:
            sys.stdout.write(f"\n  第 {attempt}/{tries} 次失败：{e}\n")
            if attempt == tries:
                raise
            time.sleep(2 * attempt)


def _endpoint_guard(endpoint: str) -> None:
    """拦掉 HuggingFace。

    本脚本拼的是 `{endpoint}/api/v1/models/{repo}/repo/files`，那是 ModelScope 的形状；
    HuggingFace 没有这个接口，`/resolve/master/` 也得改成 `/resolve/main/`。
    与其让用户对着一句 404 发呆，不如直接说清楚该怎么下。
    """
    if "huggingface" in endpoint.lower():
        raise SystemExit(
            "这个脚本只支持 ModelScope 的下载接口，不能直接改成 HuggingFace。\n"
            "\n"
            "从 HuggingFace 拿权重，二选一：\n"
            "  A) 装了 huggingface_hub 的话（本项目依赖里已经有它）：\n"
            "       hf download Qwen/Qwen3-ASR-0.6B --local-dir models/Qwen3-ASR-0.6B\n"
            "  B) 浏览器打开 https://huggingface.co/Qwen/Qwen3-ASR-0.6B/tree/main\n"
            "     把文件逐个下下来，铺到 models/Qwen3-ASR-0.6B/ 里\n"
            "\n"
            "放好之后运行 python tools/download_model.py --check 确认程序能认出来。"
        )


def _report_found(target: str) -> None:
    """下完立刻用「真正加载时的那套逻辑」再确认一遍，别等用户开麦才发现不对。"""
    sys.path.insert(0, ROOT)
    from app import model_finder

    if not model_finder.is_model_dir(Path(target)):
        print("\n✗ 这个目录还不像模型目录：必须同时有 config.json 和权重文件。")
        raise SystemExit(2)

    found, _ = model_finder.find()      # 不带参数 = 模拟程序启动时的查找
    if found:
        print(f"\n✓ 程序已能识别：{found}")
        return
    print(f"\n⚠ 目录本身没问题（{target}），但它不在 models/ 下面，程序默认找不到。")
    print(f"  启动前设一下环境变量即可：")
    print(f'     set TELEPROMPTER_MODEL={target}')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="0.6B", choices=list(REPOS))
    ap.add_argument("--dir", default=None, help="目标目录，默认 models/<repo 名>")
    ap.add_argument("--endpoint", default="https://www.modelscope.cn",
                    help="模型源，需兼容 ModelScope 的 API（不支持 HuggingFace）")
    ap.add_argument("--check", action="store_true", help="只校验，不下载")
    args = ap.parse_args()

    _endpoint_guard(args.endpoint)

    repo = REPOS[args.model]
    name = repo.split("/")[-1]
    target = args.dir or os.path.join(MODELS, name)

    print(f"模型   {repo}")
    print(f"目录   {target}")
    print(f"源     {args.endpoint}")

    files = list_files(repo, args.endpoint)
    total = sum(s for _, s in files)
    print(f"共 {len(files)} 个文件，{human(total)}\n")

    missing = 0
    for path, size in files:
        dest = os.path.join(target, path.replace("/", os.sep))
        ok = os.path.exists(dest) and os.path.getsize(dest) == size
        if ok:
            continue
        missing += 1
        if args.check:
            print(f"  缺  {path}  ({human(size)})")
        else:
            fetch(repo, path, dest, args.endpoint)

    if args.check:
        print("\n完整" if not missing else f"\n缺 {missing} 个文件，去掉 --check 重跑即可")
        if not missing:
            _report_found(target)
        return 0 if not missing else 1

    print(f"\n完成。权重在 {target}")
    _report_found(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
