"""稿件与状态的落盘。"""
from __future__ import annotations

import json

from . import config

DEMO = """大家好，我是老张。今天想跟你聊一个很多家长都问过我的问题：孩子明明很努力，成绩却一直上不去，问题到底出在哪？

我带过七届毕业班，见过太多这样的孩子。他们不是不聪明，也不是不肯下功夫，而是把力气用错了地方。每天刷题到十一点，错题本抄得整整齐齐，可下次考试同样的题型还是错。

为什么会这样？因为他在重复已经会的东西，回避真正不会的东西。抄错题是体力活，想明白错在哪才是脑力活。

所以我想跟你说的第一件事是：别急着加量，先看看孩子的时间到底花在了哪儿。今天晚上回去，你可以让他把今天做的题分成三类：会做的、蒙对的、完全不会的。分完你就知道问题在哪了。

这个动作只要十分钟，但它比你报三个补习班都有用。
"""


def _ensure_dirs() -> None:
    config.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    data: dict = {}
    try:
        data = json.loads(config.STATE_FILE.read_text("utf-8"))
    except Exception:
        data = {}
    ui = dict(config.DEFAULT_UI)
    ui.update(data.get("ui") or {})
    asr = dict(config.DEFAULT_ASR)
    asr.update(data.get("asr") or {})
    return {
        "ui": ui,
        "asr": asr,
        "last_script_id": data.get("last_script_id") or "demo",
    }


def save_state(state: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), "utf-8"
    )


def list_scripts() -> list[dict]:
    _ensure_dirs()
    out = []
    for p in sorted(config.SCRIPTS_DIR.glob("*.md")):
        text = p.read_text("utf-8", errors="replace")
        n = len([c for c in text if not c.isspace()])
        out.append(
            {
                "id": p.stem,
                "title": p.stem,
                "chars": n,
                "est_sec": int(round(n / 4.2)),
            }
        )
    return out


def script_path(sid: str):
    return config.SCRIPTS_DIR / f"{sid}.md"


# 稿件 id 直接来自 URL/前端，会拼进文件名。不挡住这几样，
# 一个 `../../app/config` 就能删到工程外面的 .md 上去。
_BAD_IN_SID = ("/", "\\", "..", "\x00", ":", "*", "?", '"', "<", ">", "|")


def is_valid_sid(sid: str) -> bool:
    if not sid or len(sid) > 80:
        return False
    if any(b in sid for b in _BAD_IN_SID):
        return False
    return sid == sid.strip() and not sid.startswith(".")


def read_script(sid: str) -> str:
    _ensure_dirs()
    p = script_path(sid)
    return p.read_text("utf-8", errors="replace") if p.exists() else ""


def write_script(sid: str, text: str) -> None:
    _ensure_dirs()
    script_path(sid).write_text(text, "utf-8")


def delete_script(sid: str) -> bool:
    """删掉一篇稿子。返回是否真的删了（不存在时返回 False，不报错）。

    只删 .md 文件本身；`state.json` 里的 last_script_id 由调用方负责改，
    因为"删的正好是当前这篇"该怎么处置属于会话层的事，存储层不该猜。
    """
    if not is_valid_sid(sid):
        return False
    p = script_path(sid)
    if not p.exists():
        return False
    p.unlink()
    return True


def seed() -> None:
    _ensure_dirs()
    if not list(config.SCRIPTS_DIR.glob("*.md")):
        write_script("demo", DEMO)
