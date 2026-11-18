#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
打包 AITeleprompter 成 zip，两种用途一次说清。

用法：
    python tools/package.py                # 只有代码（约 110 KB），适合上传开源平台
    python tools/package.py --with-model   # 代码 + 模型（约 1.8 GB），适合压缩包直发别人
    python tools/package.py --list         # 只看看会打进哪些文件，不生成 zip

产物在 dist/ 下，文件名带日期和变体：
    dist/AITeleprompter-20261116-code.zip
    dist/AITeleprompter-20261116-full.zip

为什么分两种：
    模型 model.safetensors 单个 1.75 GB，GitHub 单文件上限 100 MB，推上去必失败。
    所以「发人」和「上平台」是两套产物，不要混。

排除规则写在 EXCLUDE_DIRS / EXCLUDE_SUFFIX 里，跟 .gitignore 保持一致。
--with-model 只额外放行 models/，data/ 仍然排除（那是你自己的稿子）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

# 目录名精确匹配即整棵剪掉
EXCLUDE_DIRS = {
    "__pycache__", ".venv", "venv", "env", "dist",
    ".git", ".idea", ".vscode", ".pytest_cache", ".mypy_cache",
    "node_modules", ".ruff_cache",
}

# 后缀匹配
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".pyd", ".log", ".swp", ".tmp"}

# 文件名精确匹配
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# 这些目录默认排除；--with-model 会把 models 加回白名单
ALWAYS_EXCLUDE = {"data"}          # 用户自己的稿子 + 偏好，属于隐私
MODEL_DIR = "models"


def _iter_files(include_model: bool, include_data: bool):
    """按稳定顺序产出 (绝对路径, 归档内相对路径)。"""
    # 顶层要不要放行 models / data —— 这两个都是根目录下的固定名字
    top_gate = {}
    if not include_model:
        top_gate[MODEL_DIR] = False
    if not include_data:
        top_gate["data"] = False

    for dirpath, dirnames, filenames in os.walk(ROOT):
        here = Path(dirpath)
        at_top = here == ROOT

        # 原地剪枝：从 dirnames 里删掉，os.walk 就不会往下走
        keep = []
        for d in sorted(dirnames):
            if d in EXCLUDE_DIRS:
                continue
            if at_top and top_gate.get(d) is False:
                continue
            keep.append(d)
        dirnames[:] = keep

        for name in sorted(filenames):
            if name in EXCLUDE_FILES:
                continue
            if Path(name).suffix.lower() in EXCLUDE_SUFFIX:
                continue
            p = here / name
            try:
                p.stat()
            except OSError:
                continue
            yield p, p.relative_to(ROOT)


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} GB"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="打包 AITeleprompter 成 zip")
    ap.add_argument("--with-model", action="store_true",
                    help="把 models/ 一起打进去（约 1.8 GB，压缩包直发别人用）")
    ap.add_argument("--include-data", action="store_true",
                    help="连 data/ 一起打（默认排除；注意里面有你的稿子）")
    ap.add_argument("--list", action="store_true",
                    help="只列出会打包的文件，不生成 zip")
    ap.add_argument("-o", "--out", default=None, help="输出 zip 路径")
    args = ap.parse_args(argv)

    if not (ROOT / "run.py").exists():
        print(f"[x] 这里不像工程根目录：{ROOT}", file=sys.stderr)
        return 2

    files = list(_iter_files(args.with_model, args.include_data))
    total_raw = sum(p.stat().st_size for p, _ in files)
    variant = "full" if args.with_model else "code"

    if args.list:
        for _, rel in files:
            print(rel.as_posix())
        print(f"\n共 {len(files)} 个文件，原始体积 {_human(total_raw)}（{variant} 变体）")
        return 0

    stamp = _dt.datetime.now().strftime("%Y%m%d")
    out = Path(args.out) if args.out else DIST / f"AITeleprompter-{stamp}-{variant}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)

    # 模型权重几乎压不动，用最快档；纯代码压得动，用正常档
    level = 1 if args.with_model else 6

    print(f"[*] 打包 {len(files)} 个文件 / {_human(total_raw)} → {out}")
    done = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
        for i, (path, rel) in enumerate(files, 1):
            # 归档内统一带一层顶层目录，解压后不会散一地
            zf.write(path, arcname=(Path(ROOT.name) / rel).as_posix())
            done += 1
            if args.with_model and done % 50 == 0:
                print(f"    ... {done}/{len(files)}")

    size = out.stat().st_size
    print(f"[ok] 完成：{out}")
    print(f"     {_human(size)}  （原始 {_human(total_raw)}，压缩率 {size / total_raw * 100:.0f}%）")
    if args.with_model:
        print("\n发给别人：对方解压后双击 setup.bat 装依赖，再双击 start.bat 启动。")
    else:
        print("\n上传开源平台用这个。别人 clone 后要自己跑 python tools/download_model.py 拉模型。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
