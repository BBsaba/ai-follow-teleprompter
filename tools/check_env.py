#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""体检：这台机器上已经装好了什么、还缺什么。

为什么需要它
------------
上一版安装器是「闭着眼睛重装」：不管你上次装到哪一步，它都从
PyTorch 的第一个字节开始下。用户取消一次、断网一次，前面的 2.6 GB
就白下了 —— 这是最招人烦的地方。

这个脚本只回答一个问题：**能不能跳过某一步**。
安装器的进度窗口先调它一次，按结果把「下载 PyTorch」「装依赖」
「下模型」三步各自决定跑还是不跑。

用法
----
    python tools/check_env.py            # 人看的
    python tools/check_env.py --json     # 机器看的（安装器用）

JSON 形状（键名固定，安装器那边按名字取）：
    {
      "torch": "2.14.0+cu126" 或 null,
      "torch_cuda": true/false,
      "missing": ["fastapi"],          # 打开界面必需的
      "missing_asr": ["transformers"], # 语音识别必需的
      "model": "D:\\...\\Qwen3-ASR-0.6B" 或 null
    }

退出码：0 = 界面必需包齐了；1 = 有缺。
⚠️ 退出码只看 missing，不看 missing_asr —— 这是程序本身的分层：
   缺 transformers 还能打开界面写字，缺 fastapi 连窗口都起不来。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 打开界面就必需（run.py 里那份 _REQUIRED 是同一组，改要一起改）
REQUIRED = ("numpy", "sounddevice", "pypinyin", "fastapi", "uvicorn", "websockets")

#: 点「开始」才用到的。缺了不影响打开，但会识别不了
ASR = ("transformers", "qwen_asr", "safetensors", "huggingface_hub")

#: 期望的 torch 版本（和 installer/AI提词器.iss 里的 TorchVersion 保持一致）
TORCH_WANT = "2.14.0"


def _has(mod: str) -> bool:
    """只查「装没装」，不 import。

    为什么不 import：import transformers 要 3 秒、import torch 要 8 秒，
    而这里只是想知道在不在。真正能不能用，最后由安装器跑一次
    import 探针（见 --strict）确认。
    """
    import importlib.util

    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def torch_info() -> tuple[str | None, bool]:
    """返回 (版本串, 能不能用 CUDA)。

    ⚠️ 这个函数是**真的 import torch**：version 和 cuda 信息只能这么拿。
       慢（5–10 秒），但安装器只在开头调一次。
       装坏了（缺 DLL、版本冲突）时 import 会抛异常 —— 那就当没装，
       让它重装，比留着一个半坏的 torch 强。
    """
    try:
        import torch
    except Exception:
        return None, False

    try:
        ver = str(torch.__version__)
    except Exception:
        return None, False
    try:
        cuda = bool(torch.cuda.is_available())
    except Exception:
        cuda = False
    return ver, cuda


def find_model() -> str | None:
    """找一份**完整**的模型目录。找不到返回 None。

    优先用程序自己的查找逻辑（app/model_finder.py）—— 那是真正加载时
    用的那套，比这里另写一份判断更可信。它不在或抛异常时退回朴素检查。
    """
    sys.path.insert(0, str(ROOT))
    try:
        from app import model_finder

        found, _ = model_finder.find()
        if found:
            return str(found)
        return None
    except Exception:
        pass

    models = ROOT / "models"
    if not models.is_dir():
        return None
    for d in sorted(models.iterdir()):
        if not d.is_dir() or not (d / "config.json").is_file():
            continue
        if list(d.glob("*.safetensors")) or list(d.glob("*.bin")):
            return str(d)
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出 JSON（安装器用）")
    ap.add_argument("--strict", action="store_true",
                    help="真的 import 一遍必需包，而不是只查文件在不在")
    a = ap.parse_args(argv)

    if a.strict:
        missing = []
        for m in REQUIRED + ASR:
            try:
                __import__(m)
            except Exception:
                missing.append(m)
        miss_req = [m for m in missing if m in REQUIRED]
        miss_asr = [m for m in missing if m in ASR]
        ver, cuda = torch_info()
        model = find_model()
        info = {
            "torch": ver,
            "torch_cuda": cuda,
            "missing": miss_req,
            "missing_asr": miss_asr,
            "model": model,
        }
    else:
        ver, cuda = torch_info()
        miss_req = [m for m in REQUIRED if not _has(m)]
        miss_asr = [m for m in ASR if not _has(m)]
        model = find_model()
        info = {
            "torch": ver,
            "torch_cuda": cuda,
            "missing": miss_req,
            "missing_asr": miss_asr,
            "model": model,
        }

    if a.json:
        # ensure_ascii=False 让中文路径原样出；安装器用 ConvertFrom-Json 读，
        # PowerShell 那边按 UTF-8 解码（见 prep-ui.ps1 的 Read-Json）
        sys.stdout.write(json.dumps(info, ensure_ascii=False))
        sys.stdout.flush()
        return 0 if not miss_req else 1

    print(f"torch        {ver or '未安装'}" + ("（CUDA 可用）" if cuda else "（仅 CPU）"))
    print(f"界面必需包   {'齐了' if not miss_req else '缺：' + '、'.join(miss_req)}")
    print(f"识别依赖     {'齐了' if not miss_asr else '缺：' + '、'.join(miss_asr)}")
    print(f"模型         {model or '没找到'}")
    if ver and not ver.startswith(TORCH_WANT):
        print(f"             ⚠️ 期望 {TORCH_WANT}，当前 {ver} —— 安装器会重装 PyTorch")
    return 0 if not miss_req else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
