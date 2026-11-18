"""禁止 pytest 收集本目录的测试文件。

这些文件不是 pytest 风格：它们用 `check()` 自己计数、自己打印
「通过 N，失败 M」，没有 assert。pytest 会按 `test_*` 名字收进去，
函数体跑一遍什么都不校验，然后报「N passed」—— **假绿**，比没测更危险。

所以这里显式排除，统一入口是：

    python tests/run_all.py
"""

collect_ignore = [
    "test_script.py",
    "test_align.py",
    "test_server.py",
    "test_model_finder.py",
    "test_settings.py",
    "test_follow_e2e.py",
    "test_live.py",
    "test_ws.py",
    "test_ui.py",
]
