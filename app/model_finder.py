"""找到模型权重到底在哪个目录。

**要解决的问题**：用户在 ModelScope 网页上点「下载模型」，拿到的往往是一个压缩包，
解压出来可能是

    models/Qwen3-ASR-0.6B/model.safetensors          ← 正好（脚本下载的结果）
    models/Qwen3-ASR-0.6B/Qwen3-ASR-0.6B/...        ← 压缩包多套了一层
    models/qwen3-asr-0.6b/...                        ← 大小写不一样
    models/model.safetensors                         ← 直接把内容倒进了 models/

如果只认死一个路径，上面后三种都会在 `from_pretrained` 里抛出一段 transformers 的
堆栈，用户根本看不出是"文件夹放错地方了"。

所以这里不认名字，只认**内容**：一个目录同时有 `config.json` 和权重文件，它就是模型目录。

判定完全靠文件名和目录结构，不加载 torch，因此可以被单元测试直接调用。
"""
from __future__ import annotations

import os
from pathlib import Path

from . import config

#: 只认这几种权重文件名。分片的 `model-00001-of-00003.safetensors` 另行判定
WEIGHT_EXACT = ("model.safetensors", "pytorch_model.bin")

#: 模型目录里必须有的配置
CONFIG_FILE = "config.json"


class ModelMissing(Exception):
    """找不到模型权重。

    `str(e)` 是给**终端**看的完整说明（找过哪些地方、怎么解决）；
    `user_msg` 是给**界面状态条**看的两行短提示——侧栏只有 380 px 宽，塞不下细节。
    """

    def __init__(self, detail: str, user_msg: str):
        super().__init__(detail)
        self.user_msg = user_msg


def _has_weight_file(p: Path) -> bool:
    for name in WEIGHT_EXACT:
        if (p / name).is_file():
            return True
    # 分片权重：model-00001-of-00003.safetensors
    try:
        for f in p.iterdir():
            if f.is_file() and f.suffix == ".safetensors" and f.name.startswith("model-"):
                return True
    except OSError:
        return False
    return False


def is_model_dir(p: Path) -> bool:
    """这个目录是不是一个能直接喂给 from_pretrained 的模型目录。"""
    try:
        return p.is_dir() and (p / CONFIG_FILE).is_file() and _has_weight_file(p)
    except OSError:
        return False


def candidates(models_dir: Path | None = None) -> list[Path]:
    """按「可能性从高到低」列出候选目录，去重保序。

    顺序是刻意排的：先默认位置（脚本下载的结果），再 `models/` 本身
    （用户把内容直接倒进去），然后任意一层子目录（名字随便叫），
    最后一层子目录的下一层（压缩包多套的那层）。
    """
    models_dir = Path(models_dir or config.MODELS_DIR)
    out: list[Path] = [models_dir / "Qwen3-ASR-0.6B"]

    if models_dir.is_dir():
        out.append(models_dir)
        try:
            kids = sorted(x for x in models_dir.iterdir() if x.is_dir())
        except OSError:
            kids = []
        out += kids
        for k in kids:
            try:
                out += sorted(x for x in k.iterdir() if x.is_dir())
            except OSError:
                continue

    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def find(explicit: str | os.PathLike | None = None,
         models_dir: Path | None = None) -> tuple[Path | None, list[Path]]:
    """定位模型目录。

    `explicit` 非空时**只认它**——用户既然显式指定了 `TELEPROMPTER_MODEL`，
    就不该偷偷改用别的目录，否则"我明明指了另一份权重，怎么还是旧的"更难查。

    `models_dir` 只为测试留口子，正常调用不用传。

    返回 `(找到的目录 or None, 找过的目录列表)`。
    """
    if explicit:
        p = Path(explicit).expanduser()
        return (p if is_model_dir(p) else None), [p]

    tried: list[Path] = []
    for p in candidates(models_dir):
        tried.append(p)
        if is_model_dir(p):
            return p, tried
    return None, tried


def default_dir() -> Path:
    """脚本下载时用的标准位置。"""
    return config.MODELS_DIR / "Qwen3-ASR-0.6B"


def _dir_size(p: Path) -> int:
    total = 0
    try:
        for f in p.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except OSError:
        pass
    return total


def scan(models_dir: Path | None = None) -> list[dict]:
    """列出 models/ 下所有能被认成模型的目录，给设置页的下拉用。

    扫描范围与 `candidates()` 一致（最多两层），不会去翻整个磁盘。
    """
    models_dir = Path(models_dir or config.MODELS_DIR)
    out: list[dict] = []
    seen: set[Path] = set()
    for p in candidates(models_dir):
        if p in seen or not is_model_dir(p):
            continue
        seen.add(p)
        out.append({
            "path": str(p),
            "name": p.name,
            "gb": round(_dir_size(p) / 1024 ** 3, 2),
            "is_default": p == default_dir(),
        })
    return out


def explain(tried: list[Path]) -> str:
    """终端里打印的完整说明。"""
    lines = ["没有找到模型权重。", "", "找过这些位置（都不符合）："]
    lines += [f"  ✗ {p}" for p in tried]
    lines += [
        "",
        "一个目录要被认成模型，必须同时有这两样：",
        f"  · {CONFIG_FILE}",
        "  · model.safetensors（或 pytorch_model.bin / model-*-of-*.safetensors）",
        "",
        "怎么解决（三选一）：",
        "  1) 自动下载，最省事（约 1.8 GB，支持断点续传）",
        "       python tools/download_model.py",
        "",
        "  2) 手动下载，放到默认位置",
        f"       {default_dir()}",
        "     从 https://modelscope.cn/models/Qwen/Qwen3-ASR-0.6B 把 10 个文件下下来，",
        "     直接铺在这个目录里——**不要再套一层同名文件夹**。",
        "",
        "  3) 模型已经放在别处，用环境变量指过去（只认这一个目录）",
        "       set TELEPROMPTER_MODEL=D:\\某处\\Qwen3-ASR-0.6B",
    ]
    return "\n".join(lines)


def explain_short() -> str:
    """界面状态条里显示的两行。侧栏窄，别写长句。"""
    return ("没找到模型权重。\n"
            "把 Qwen3-ASR-0.6B 的文件夹放进 models/ 里，"
            "或在本目录运行 python tools/download_model.py")
