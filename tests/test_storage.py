"""磁盘占用统计与清理的单测。`python tests/test_storage.py`

覆盖需求 C 的三条要害：
  · 日志**轮转**（不轮转就会无限长，这正是用户担心的事）
  · 清理**只动日志**，一篇稿子都不能少
  · 启动清扫**不碰 pip 下载缓存**（那是重装补依赖时要用的 240 MB）
"""
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, storage

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


@contextmanager
def sandbox():
    """把 storage 用到的那几个路径全部指到临时目录。

    ⚠️ `config.ROOT` / `config.LOG_FILES` 是模块级常量，改了就是**全局**改。
    所以用完必须在 finally 里还原 —— 否则同一个进程里排在后面的用例
    （以及 run_all 里后面的文件）会看到错乱的路径，症状还很难归因。

    故意建两个临时目录：`tmp` 当假安装目录，`tmpout` 当假 %TEMP%。
    真实环境里那个备用日志就在安装目录**外面**，混在一起会让「程序本体」
    这一行把它重复算一遍。
    """
    tmp = Path(tempfile.mkdtemp(prefix="aitp-stor-"))
    tmpout = Path(tempfile.mkdtemp(prefix="aitp-tmplog-"))
    saved = (config.ROOT, config.LOG_FILES, config.SCRIPTS_DIR,
             config.MODELS_DIR, storage.INSTALL_CACHE_DIR)
    try:
        (tmp / "data" / "scripts").mkdir(parents=True)
        (tmp / "models").mkdir()
        config.ROOT = tmp
        config.SCRIPTS_DIR = tmp / "data" / "scripts"
        config.MODELS_DIR = tmp / "models"
        config.LOG_FILES = (tmp / "data" / "launch.log",
                            tmpout / "AITeleprompter-launch.log")
        storage.INSTALL_CACHE_DIR = tmp / "_tmp"
        yield tmp
    finally:
        (config.ROOT, config.LOG_FILES, config.SCRIPTS_DIR,
         config.MODELS_DIR, storage.INSTALL_CACHE_DIR) = saved
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmpout, ignore_errors=True)


def test_rotate():
    print("[日志轮转]")
    with sandbox():
        log = config.LOG_FILES[0]
        log.parent.mkdir(parents=True, exist_ok=True)

        # ① 小文件不动它
        log.write_text("小日志", "utf-8")
        check("小文件不轮转", storage.rotate(log) is None and log.exists())

        # ② 超过上限 → 改名成 .1，原文件让位
        log.write_text("x" * (storage.MAX_LOG_BYTES + 1), "utf-8")
        dst = storage.rotate(log)
        check("超过 512 KB 会轮转", dst is not None and dst.name == "launch.log.1", dst)
        check("轮转后原文件不在", not log.exists())
        check(".1 里是原来的内容", dst is not None and dst.stat().st_size > storage.MAX_LOG_BYTES)

        # ③ open_log = 轮转 + 新建 + 追加（⛔ 不能是覆盖，否则上一个实例的记录被抹掉）
        with storage.open_log(log) as sink:
            sink.write("这次启动\n")
        check("open_log 建出了新文件", log.exists() and log.read_text("utf-8") == "这次启动\n")
        with storage.open_log(log) as sink:
            sink.write("第二次\n")
        check("open_log 是追加不是覆盖", "这次启动" in log.read_text("utf-8"))

        # ④ 崩溃记录不能被轮转卷走：写完之后，不管轮到哪个文件里，都必须还在
        log.write_text("y" * storage.MAX_LOG_BYTES, "utf-8")
        with storage.open_log(log) as sink:
            sink.write("[崩溃] 故意写的一条\n")
        texts = "".join(p.read_text("utf-8", errors="replace")
                        for p in storage.log_paths() if p.exists())
        check("崩溃记录没被卷走（原文件或 .1 里还在）", "[崩溃] 故意写的一条" in texts)


def test_clean_logs():
    print("[清理日志]")
    with sandbox():
        log = config.LOG_FILES[0]
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("a" * 100, "utf-8")
        (log.parent / "launch.log.1").write_text("b" * 100, "utf-8")
        temp_log = config.LOG_FILES[1]
        temp_log.parent.mkdir(parents=True, exist_ok=True)
        temp_log.write_text("c" * 100, "utf-8")
        keep = config.SCRIPTS_DIR / "keep.md"
        keep.write_text("我的稿子", "utf-8")

        # 模拟「launch.log 正被这个进程占着」——run.py 的 stdout 就挂在它上面，
        # 真实环境里点「清理日志」走的正是这条路。
        holder = open(log, "a", encoding="utf-8")
        try:
            did = storage.clean_logs()
        finally:
            holder.close()

        check("没有失败项", not did["failed"], did["failed"])
        check("被占用的那个：删不掉就清空", (not log.exists()) or log.stat().st_size == 0,
              log.stat().st_size if log.exists() else "已删除")
        check(".1 被删掉", not (log.parent / "launch.log.1").exists())
        check("%TEMP% 那份也清了", not temp_log.exists())
        check("⛔ 稿件一篇不少", keep.exists() and keep.read_text("utf-8") == "我的稿子")
        check("清理结果说清楚了每个文件的下场",
              bool(did["deleted"] or did["truncated"]), did)


def test_clean_whitelist():
    print("[清理白名单]")
    check("只有 logs / install_cache 可清",
          set(storage.CLEANERS) == {"logs", "install_cache"}, list(storage.CLEANERS))
    check("⛔ 没有任何删稿件的入口",
          not any("script" in k.lower() for k in storage.CLEANERS), list(storage.CLEANERS))

    with sandbox():
        cache = storage.INSTALL_CACHE_DIR
        (cache / "pipcache").mkdir(parents=True)
        (cache / "pipcache" / "torch.whl").write_bytes(b"0" * 64)
        did = storage.CLEANERS["install_cache"]()
        check("安装缓存整个删掉", not cache.exists(), did)
        check("没报失败", not did["failed"], did["failed"])


def test_sweep_startup_junk():
    print("[启动清扫安装残留]")
    with sandbox() as tmp:
        (tmp / "is-ABC123.tmp").write_bytes(b"0" * 100)
        (tmp / "is-DEF456.tmp").write_bytes(b"0" * 100)
        (tmp / "install.log").write_text("别动我", "utf-8")
        cache = storage.INSTALL_CACHE_DIR
        (cache / "pipcache").mkdir(parents=True)
        (cache / "pipcache" / "torch-2.8.whl").write_bytes(b"0" * 100)
        (cache / "progress.txt").write_text("12%", "utf-8")
        (cache / "cancel.flag").write_text("", "utf-8")

        gone = storage.sweep_startup_junk()

        check("is-*.tmp 清掉了",
              not (tmp / "is-ABC123.tmp").exists() and not (tmp / "is-DEF456.tmp").exists())
        check("进度/标志文件清掉了",
              not (cache / "progress.txt").exists() and not (cache / "cancel.flag").exists())
        check("⛔ pip 下载缓存保留（重装补依赖要用它，240 MB）",
              (cache / "pipcache" / "torch-2.8.whl").exists())
        check("_tmp 目录还在（里面还有缓存，不能整个删）", cache.is_dir())
        check("install.log 不许动", (tmp / "install.log").exists())
        check("返回值说清了删掉哪几项", len(gone) >= 3, gone)

        # 缓存也空了的时候，空目录顺手收掉
        shutil.rmtree(cache / "pipcache")
        storage.sweep_startup_junk()
        check("_tmp 空了就把目录也收掉", not cache.exists())


def test_scan():
    print("[数据占用统计]")
    with sandbox() as tmp:
        (config.SCRIPTS_DIR / "a.md").write_text("x" * 500, "utf-8")
        (config.SCRIPTS_DIR / "b.md").write_text("y" * 300, "utf-8")
        mdl = config.MODELS_DIR / "Qwen3-ASR-0.6B"
        mdl.mkdir()
        (mdl / "model.safetensors").write_bytes(b"0" * 2048)
        log = config.LOG_FILES[0]
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("z" * 128, "utf-8")
        (tmp / "app").mkdir()
        (tmp / "app" / "main.py").write_text("0" * 64, "utf-8")

        st = storage.scan()
        rows = {r["key"]: r for r in st["rows"]}

        check("四行固定都在", set(rows) >= {"scripts", "logs", "models", "program"}, list(rows))
        check("稿件 2 篇 800 字节",
              rows["scripts"]["count"] == 2 and rows["scripts"]["bytes"] == 800, rows["scripts"])
        check("日志 1 个 128 字节",
              rows["logs"]["count"] == 1 and rows["logs"]["bytes"] == 128, rows["logs"])
        check("模型 2048 字节（含子目录）", rows["models"]["bytes"] == 2048, rows["models"])
        check("程序本体不含 data/models", rows["program"]["bytes"] == 64, rows["program"]["bytes"])
        check("合计 = 各行相加", st["total"] == sum(r["bytes"] for r in st["rows"]), st["total"])
        check("稿件那行不给清理按钮", rows["scripts"]["cleanable"] is False)
        check("日志那行可以清理", rows["logs"]["cleanable"] is True)
        check("每行都带一句说明", all(r.get("note") for r in st["rows"]))

        # 装了缓存之后才会多出第五行
        (storage.INSTALL_CACHE_DIR / "pipcache").mkdir(parents=True)
        (storage.INSTALL_CACHE_DIR / "pipcache" / "a.whl").write_bytes(b"0" * 10)
        st2 = storage.scan()
        check("有安装缓存时才多出那一行",
              "install_cache" in {r["key"] for r in st2["rows"]}, list(st2["rows"]))


def main():
    test_rotate()
    test_clean_logs()
    test_clean_whitelist()
    test_sweep_startup_junk()
    test_scan()
    print(f"\n通过 {OK}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
