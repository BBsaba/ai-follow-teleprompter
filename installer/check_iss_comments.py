"""扫 Inno Setup 脚本里「Pascal 注释被提前截断」的坑。

Inno 的 [Code] 段是 Pascal，注释用 { ... }。
如果在注释里写了 {app} 这种常量，第一个 } 就把注释结束了，
后面的文字变成代码 → 报 "Syntax error"，而且行号指向注释中间，
很难看出是注释的问题（我已经踩了三次）。

本脚本只检查 [Code] 段，[Setup]/[Files] 等段的 {} 是常量，合法。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def check(path: Path) -> int:
    text = path.read_text("utf-8-sig")
    lines = text.splitlines()

    # 找到 [Code] 段
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "[code]":
            start = i + 1
            break
    if start is None:
        print(f"{path.name}: 没有 [Code] 段")
        return 0

    problems = 0
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 坑 2：[Setup] 这种方括号标签，即使在注释行里也会被 ISCC 当成段头，
        # 报的是 "Invalid section tag"，行号指过来，但完全看不出是注释的锅。
        # 同一条规则也适用于「数组参数换行后顶格写 [ ]」的写法。
        if (stripped.startswith("{") or stripped.startswith("//")) \
                and re.search(r"\[[A-Za-z][A-Za-z0-9_]*\]", line):
            problems += 1
            print(f"  ⚠ {path.name}:{i + 1} 注释里出现 [xxx]，会被当成段标签")
            print(f"      {stripped[:90]}")
            i += 1
            continue

        if stripped.startswith("[") and not stripped.startswith("[Code]"):
            problems += 1
            print(f"  ⚠ {path.name}:{i + 1} 行首是 [，会被当成段标签（数组参数别换行顶格写）")
            print(f"      {stripped[:90]}")
            i += 1
            continue

        for col, ch in enumerate(line):
            if ch != "{":
                continue
            # 从 { 开始找配对的 }
            depth_issue = False
            j, c2 = i, col + 1
            while j < len(lines):
                seg = lines[j][c2:] if j == i else lines[j]
                k = seg.find("}")
                inner = seg[:k] if k >= 0 else seg
                if "{" in inner:
                    depth_issue = True
                    break
                if k >= 0:
                    break
                j += 1
                c2 = 0
            if depth_issue:
                problems += 1
                print(f"  ⚠ {path.name}:{i + 1}:{col + 1} 注释里又出现了 {{ —— 会被提前截断")
                print(f"      {line.strip()[:90]}")
                break     # 一行报一次就够
        i += 1

    if problems == 0:
        print(f"  {path.name}: [Code] 段 {len(lines) - start} 行，注释没问题")
    return problems


def main() -> int:
    # 允许直接传路径：iss 在 installer/ 子目录里，构建脚本从仓库根调用，
    # 只扫当前目录会找不到文件、然后一声不响地通过。
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = [Path(a) for a in args] if args else sorted(Path(".").glob("*.iss"))
    if not files:
        print("没找到 .iss（可在命令行指定路径，如 installer/AI提词器.iss）")
        return 1
    total = sum(check(f) for f in files)
    print(f"\n共发现 {total} 处")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
