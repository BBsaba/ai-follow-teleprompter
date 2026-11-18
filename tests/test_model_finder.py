"""模型目录定位：验证「把模型丢进 models/ 就能用」这件事真的成立。

不起服务、不加载 torch、不碰网络 —— 只在临时目录里造几个假模型目录。
这是「别人 clone 下来能不能开箱即用」的第一道闸。

    python tests/test_model_finder.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import model_finder  # noqa: E402

OK = 0
FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


def mk_model(p: Path, weight: str = "model.safetensors") -> Path:
    """造一个「看起来像模型」的目录：config.json + 一个权重文件。"""
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.json").write_text("{}", encoding="utf-8")
    (p / weight).write_bytes(b"\0" * 16)
    return p


# ---------------- 判定：什么样的目录才算模型 ----------------
def test_is_model_dir(tmp: Path):
    print("[目录判定]")
    check("标准目录（config.json + model.safetensors）",
          model_finder.is_model_dir(mk_model(tmp / "a")))
    check("pytorch_model.bin 也认",
          model_finder.is_model_dir(mk_model(tmp / "b", "pytorch_model.bin")))
    check("分片权重也认",
          model_finder.is_model_dir(
              mk_model(tmp / "c", "model-00001-of-00003.safetensors")))

    only_conf = tmp / "d"
    only_conf.mkdir(parents=True)
    (only_conf / "config.json").write_text("{}", encoding="utf-8")
    check("只有 config.json 不算", not model_finder.is_model_dir(only_conf))

    only_w = tmp / "e"
    only_w.mkdir(parents=True)
    (only_w / "model.safetensors").write_bytes(b"\0" * 16)
    check("只有权重不算", not model_finder.is_model_dir(only_w))

    empty = tmp / "f"
    empty.mkdir(parents=True)
    check("空目录不算", not model_finder.is_model_dir(empty))
    check("不存在的路径不算", not model_finder.is_model_dir(tmp / "nope"))

    plain = tmp / "g.txt"
    plain.write_text("x", encoding="utf-8")
    check("普通文件不算", not model_finder.is_model_dir(plain))


# ---------------- 查找：四种真实的摆放方式 ----------------
def test_find_layouts(tmp: Path):
    print("[摆放方式]")

    # 1) 脚本下载的结果：models/Qwen3-ASR-0.6B/
    m1 = tmp / "m1"
    mk_model(m1 / "Qwen3-ASR-0.6B")
    found, _ = model_finder.find(models_dir=m1)
    check("标准位置能命中", found == m1 / "Qwen3-ASR-0.6B", found)

    # 2) 压缩包多套了一层：models/下载/Qwen3-ASR-0.6B/
    m2 = tmp / "m2"
    mk_model(m2 / "下载" / "Qwen3-ASR-0.6B")
    found, _ = model_finder.find(models_dir=m2)
    check("多套一层也能命中", found == m2 / "下载" / "Qwen3-ASR-0.6B", found)

    # 3) 大小写不一样：models/qwen3-asr-0.6b/
    m3 = tmp / "m3"
    mk_model(m3 / "qwen3-asr-0.6b")
    found, _ = model_finder.find(models_dir=m3)
    check("文件夹改名也能命中", found is not None, found)

    # 4) 直接把内容倒进了 models/
    m4 = tmp / "m4"
    mk_model(m4)
    found, _ = model_finder.find(models_dir=m4)
    check("内容直接放在 models/ 也能命中", found == m4, found)

    # 5) 什么都没有
    m5 = tmp / "m5"
    m5.mkdir(parents=True)
    found, tried = model_finder.find(models_dir=m5)
    check("找不到时返回 None", found is None, found)
    check("找不到时回去路径列表非空", len(tried) > 0, tried)

    # 6) 显式指定且有效
    m6 = tmp / "m6"
    real = mk_model(m6 / "某个名字")
    found, tried = model_finder.find(explicit=str(real), models_dir=m6)
    check("显式指定时用它", found == real, found)
    check("显式指定时只试了那一个", len(tried) == 1, tried)

    # 7) 显式指定但无效 —— 不许偷偷回退到 models/ 里的好目录
    m7 = tmp / "m7"
    mk_model(m7 / "Qwen3-ASR-0.6B")
    found, _ = model_finder.find(explicit=str(m7 / "空目录"), models_dir=m7)
    check("显式指定失效时不回退", found is None, found)


# ---------------- 候选顺序 ----------------
def test_candidates(tmp: Path):
    print("[候选顺序]")
    m = tmp / "cand"
    mk_model(m / "B")
    cands = model_finder.candidates(m)
    check("第一候选是标准位置",
          cands[0] == m / "Qwen3-ASR-0.6B", cands[0])
    check("没有重复项", len(cands) == len(set(cands)), cands)
    check("包含 models/ 本身", m in cands, cands)


# ---------------- 报错文案 ----------------
def test_explain(tmp: Path):
    print("[报错文案]")
    m = tmp / "err"
    m.mkdir(parents=True)
    _, tried = model_finder.find(models_dir=m)
    msg = model_finder.explain(tried)

    check("列出了每个找过的路径", all(str(p) in msg for p in tried))
    check("给出自动下载命令", "download_model.py" in msg, msg[:80])
    check("说明什么算模型目录", "config.json" in msg)
    check("给出默认放置目录",
          str(model_finder.default_dir()) in msg)
    check("给出环境变量兜底", "TELEPROMPTER_MODEL" in msg)

    short = model_finder.explain_short()
    check("短文案是两行", short.count("\n") == 1, repr(short))
    check("短文案够短（侧栏 380px）", len(short) < 140, len(short))
    check("短文案不夹细节", "找过这些位置" not in short)


# ---------------- 异常类型 ----------------
def test_exception():
    print("[异常类型]")
    e = model_finder.ModelMissing("完整说明", "短提示")
    check("str() 给终端看的", "完整说明" in str(e))
    check("user_msg 给界面看的", e.user_msg == "短提示")
    check("两者不同", str(e) != e.user_msg)


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_is_model_dir(tmp / "t1")
        test_find_layouts(tmp / "t2")
        test_candidates(tmp / "t3")
        test_explain(tmp / "t4")
        test_exception()
    print(f"\n通过 {OK}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
