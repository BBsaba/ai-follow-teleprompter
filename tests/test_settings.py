"""设置页的后端契约：麦克风 / 模型 / 推理后端。

不起服务、不加载模型。设备相关的断言会按「本机到底有没有麦克风」自适应——
CI 机器上没有声卡是常态，不能因此把测试跑红，也不能假装测过了。

    python tests/test_settings.py
"""
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, server, store  # noqa: E402
from app.asr import AsrEngine  # noqa: E402

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


# ---------------- 默认值 ----------------
def test_defaults():
    print("[默认值]")
    check("有 DEFAULT_ASR 段", isinstance(config.DEFAULT_ASR, dict))
    for k in ("mic_index", "model_dir", "device", "dtype"):
        check(f"包含 {k}", k in config.DEFAULT_ASR)
    check("麦克风默认 = 系统默认", config.DEFAULT_ASR["mic_index"] is None)
    check("模型默认 = 自动找", config.DEFAULT_ASR["model_dir"] is None)
    check("设备默认 auto", config.DEFAULT_ASR["device"] == "auto")
    check("精度默认 auto", config.DEFAULT_ASR["dtype"] == "auto")

    st = store.load_state()
    check("state 里有 asr 段", "asr" in st, list(st))
    check("state.asr 合并了默认值",
          all(k in st["asr"] for k in config.DEFAULT_ASR), st.get("asr"))


# ---------------- 麦克风编号校验 ----------------
def test_mic_normalize():
    print("[麦克风编号]")
    ids = [d["id"] for d in server.audio.list_inputs()]
    print(f"       （本机读到 {len(ids)} 个输入设备）")

    out, err = server._normalize_asr({"mic_index": ""})
    check("空字符串 → 系统默认", err is None and out["mic_index"] is None)
    out, err = server._normalize_asr({"mic_index": None})
    check("None → 系统默认", err is None and out["mic_index"] is None)

    if ids:
        first = ids[0]
        out, err = server._normalize_asr({"mic_index": first})
        check(f"接受存在的设备 {first}", err is None and out["mic_index"] == first)
        out, err = server._normalize_asr({"mic_index": str(first)})
        check("接受字符串编号并转成整数",
              err is None and out["mic_index"] == first)
    else:
        print("       本机没有输入设备，跳过「接受有效编号」两项")

    # 0 是个真实编号，绝不能被 `or None` 之类的写法吞成「系统默认」
    if 0 in ids:
        out, err = server._normalize_asr({"mic_index": 0})
        check("0 号设备不会被当成空值",
              err is None and out["mic_index"] == 0, out)

    _, err = server._normalize_asr({"mic_index": 99999})
    check("拒绝不存在的编号", err is not None)
    _, err = server._normalize_asr({"mic_index": "abc"})
    check("拒绝非数字", err is not None)


# ---------------- 模型路径校验 ----------------
def test_model_normalize():
    print("[模型路径]")
    out, err = server._normalize_asr({"model_dir": ""})
    check("空字符串 → 自动找", err is None and out["model_dir"] is None)
    out, err = server._normalize_asr({"model_dir": "   "})
    check("全空格 → 自动找", err is None and out["model_dir"] is None)

    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "随便叫什么都行"
        good.mkdir()
        (good / "config.json").write_text("{}", encoding="utf-8")
        (good / "model.safetensors").write_bytes(b"\0" * 8)

        out, err = server._normalize_asr({"model_dir": str(good)})
        check("接受合法模型目录", err is None and out["model_dir"] == str(good))

        empty = Path(td) / "空的"
        empty.mkdir()
        _, err = server._normalize_asr({"model_dir": str(empty)})
        check("拒绝缺文件的目录", err is not None)
        check("错误里说清缺什么", err and "config.json" in err, err)

        _, err = server._normalize_asr({"model_dir": str(Path(td) / "不存在")})
        check("拒绝不存在的路径", err is not None)


# ---------------- 枚举值校验 ----------------
def test_enum_normalize():
    print("[枚举值]")
    for bad in ("gpu", "cuda:1", "", "CPU"):
        _, err = server._normalize_asr({"device": bad})
        check(f"拒绝 device={bad!r}", err is not None)
    for good in config.ASR_CHOICES["device"]:
        _, err = server._normalize_asr({"device": good})
        check(f"接受 device={good}", err is None)

    for bad in ("int8", "auto2"):
        _, err = server._normalize_asr({"dtype": bad})
        check(f"拒绝 dtype={bad!r}", err is not None)
    for good in config.ASR_CHOICES["dtype"]:
        _, err = server._normalize_asr({"dtype": good})
        check(f"接受 dtype={good}", err is None)

    # 不认识的键不该被写进去
    out, err = server._normalize_asr({"乱写": 1})
    check("忽略未知字段", err is None and out == {}, out)


# ---------------- 引擎：变了才卸载 ----------------
def test_engine_reconfigure():
    print("[引擎重配置]")
    e = AsrEngine()
    check("同样的值 → 不算变化", e.reconfigure(None, "auto", "auto") is False)
    check("换设备 → 算变化", e.reconfigure(None, "cpu", "auto") is True)
    check("再存一次 cpu → 不算变化", e.reconfigure(None, "cpu", "auto") is False)
    check("换精度 → 算变化", e.reconfigure(None, "cpu", "float32") is True)

    # 自动找（None）找到具体路径后，偏好不能跟着被改写，
    # 否则下次保存会把「自动」误判成「换成了具体路径」，白卸载一次模型
    e2 = AsrEngine()
    e2.model_dir = r"D:\some\resolved\path"   # 模拟 load() 之后的状态
    check("解析出的路径不污染偏好", e2.reconfigure(None, "auto", "auto") is False)


# ---------------- 采集器换设备 ----------------
def test_apply_settings():
    print("[应用设置]")
    from app.listener import Listener

    async def _noop(msg):
        return None

    lis = Listener(_noop)
    try:
        res = lis.apply_settings({"mic_index": None, "model_dir": None,
                                  "device": "auto", "dtype": "auto"})
        check("返回两个变更标志",
              set(res) == {"mic_changed", "model_changed"}, res)
        check("首次应用后 mic_index 已记录",
              lis.mic_index == lis.rec.device)
        check("状态里带 mic_index", "mic_index" in lis.status())
    finally:
        lis.pool.shutdown(wait=False)


# ---------------- 录制中拒绝改设置 ----------------
def test_busy_guard():
    print("[录制中锁定]")

    async def go():
        old_on, old_loading = server.listener.on, server.listener.loading
        try:
            server.listener.on = True
            r1 = await server.api_put_settings({"mic_index": None})
            server.listener.on = False
            server.listener.loading = True
            r2 = await server.api_put_settings({"mic_index": None})
            return r1, r2
        finally:
            server.listener.on, server.listener.loading = old_on, old_loading

    r1, r2 = asyncio.run(go())
    check("开麦时 409", getattr(r1, "status_code", None) == 409, r1)
    check("加载模型时也 409", getattr(r2, "status_code", None) == 409, r2)


# ---------------- 页面资源 ----------------
def test_pages():
    print("[页面]")
    html = (ROOT / "web" / "settings.html").read_text(encoding="utf-8")
    for eid in ("micSel", "btnMicRefresh", "btnMicTest", "micVu",
                "modelSel", "btnModelScan", "modelPath", "btnPathCheck",
                "devSel", "dtypeSel", "btnSave", "busyBar", "toast"):
        check(f"页面含 #{eid}", f'id="{eid}"' in html)

    check("引用了 settings.js", "/static/settings.js" in html)
    check("引用了 settings.css", "/static/settings.css" in html)
    check("settings.js 存在", (ROOT / "web" / "settings.js").is_file())
    check("settings.css 存在", (ROOT / "web" / "settings.css").is_file())

    js = (ROOT / "web" / "settings.js").read_text(encoding="utf-8")
    check("JS 会读 /api/settings", "/api/settings" in js)
    check("JS 会调试音接口", "/api/mic/test" in js)

    css = (ROOT / "web" / "settings.css").read_text(encoding="utf-8")
    check("CSS 处理了 [hidden] 被 display:grid 覆盖的坑",
          ".field[hidden]" in css)

    con = (ROOT / "web" / "console.html").read_text(encoding="utf-8")
    check("控制台头部有设置入口", 'id="btnSettings"' in con)


def main():
    test_defaults()
    test_mic_normalize()
    test_model_normalize()
    test_enum_normalize()
    test_engine_reconfigure()
    test_apply_settings()
    test_busy_guard()
    test_pages()
    print(f"\n通过 {OK}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
