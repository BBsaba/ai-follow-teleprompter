"""集中配置。所有可调数值都在这里，别散落到各处。

路径全部相对本文件推导，整个目录搬到哪里都能跑（打包发给别人/上传开源都靠这条）。
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCRIPTS_DIR = DATA_DIR / "scripts"
STATE_FILE = DATA_DIR / "state.json"
WEB_DIR = ROOT / "web"
MODELS_DIR = ROOT / "models"

#: 启动日志的两个候选位置。run.py 按顺序取第一个**写得进去**的。
#: 第一个是正常位置（跟着安装目录走，用户能自己翻）；装到不可写目录时退到 %TEMP%。
#: ⛔ 两张表要一起维护：`app/storage.py` 的「数据占用」和「清理日志」按同一份算，
#: 只加一处就会出现"面板显示没有日志，实际 %TEMP% 里躺着一个"。
LOG_FILES = (
    DATA_DIR / "launch.log",
    Path(os.environ.get("TEMP") or ".") / "AITeleprompter-launch.log",
)

# 权重默认落在 models/ 下。
# ASR_MODEL 只是「期望位置」——下载脚本的目标、报错文案里都引用它；
# 真正加载时由 app/model_finder.py 在 models/ 里**按内容找**，
# 所以文件夹叫别的名字、或者被压缩包多套了一层，都能用。
# 想固定用别处的权重，设环境变量 TELEPROMPTER_MODEL：一旦设了，就只认那一个目录。
ASR_MODEL_EXPLICIT = os.environ.get("TELEPROMPTER_MODEL") or None
ASR_MODEL = Path(
    ASR_MODEL_EXPLICIT or str(MODELS_DIR / "Qwen3-ASR-0.6B")
).expanduser()

DEFAULT_UI = {
    # 排版
    "font_px": 64,
    "font_min": 24,
    "font_max": 160,
    "font_step": 2,
    "per_line": 14,
    "per_line_min": 8,
    "per_line_max": 20,
    "line_height": 1.9,
    # 红线
    "cue_ratio": 0.42,
    "cue_ratio_min": 0.15,
    "cue_ratio_max": 0.70,
    "cue_gap_px": 8,
    "cue_thickness": 2,
    # 配色
    "bg": "#000000",
    "fg": "#FFFFFF",
    "read_color": "#7A7A7A",
    "cue_color": "#FF2D2D",
    "cue_paused_color": "#8A8A8A",
    # 其它
    "mirror": False,
    "cps": 4.2,          # 自动滚动速度：字/秒
    # AI 跟随的「跟随范围」：只在当前位置前后各 N 行以内找稿子，**超出这个范围
    # 的匹配一律不跟**。它防的是「某个词跟十几行以后的内容撞车，屏幕一下跳一大段」。
    #
    # ⚠️ 单位是「行」不是「字」：用户看到的是行，调的是行。实际搜索半径 = max(
    #    N × per_line, 3 × per_line, 40) 个字 —— 后两项是下限，见 align.py 的
    #    MIN_RADIUS：半径比「一段话」还短时窗口装不下当前这句，跟读会直接停摆。
    #    所以改「每行 N 字」时范围跟着变，符合直觉；但调不到 40 字以下。
    # ⚠️ 别改成「每秒几行」的速度限制（v2.3.x 试过，见开发规划 §21）：
    #    速度只让它慢一点，该跳还是会跳过去；范围才是直接不认。
    "follow_lines": 8,
    # 最小 3 行：1 行 = 20 字在每行 20 字时连一句话都装不下（实测跟读停摆）
    "follow_lines_min": 3,
    "follow_lines_max": 50,
    # 推进方式，二选一，不会同时生效：
    #   auto = 按 cps 匀速自动滚动（不需要麦克风）
    #   ai   = 只在识别到稿子内容时才动，不说话就不动
    "follow_mode": "auto",
}

MOTION = {"tau_fwd": 0.09, "tau_back": 0.22}
TICK_HZ = 60
PUSH_HZ = 30
HOST = "127.0.0.1"

# 默认 8756。想同时跑两份（比如解压出来的新副本试一下）设环境变量 TELEPROMPTER_PORT
PORT = int(os.environ.get("TELEPROMPTER_PORT", "8756"))

# ---------------- 音频采集 ----------------
AUDIO = {
    "sr": 16000,          # Qwen3-ASR 要 16 kHz
    "block_ms": 100,      # 每块毫秒数，决定最小延迟粒度
    "channels": 1,
    "device": None,       # None = 系统默认输入；可在控制台切换
}

# ---------------- 用户可在设置页改的项 ----------------
# 落盘在 data/state.json 的 "asr" 段。默认值 = 「什么都不用管也能跑」。
DEFAULT_ASR = {
    "mic_index": None,    # sounddevice 的输入设备索引；None = 系统默认输入
    "model_dir": None,    # 模型目录；None = 在 models/ 里按内容自动找
    "device": "auto",     # auto / cuda:0 / cpu
    "dtype": "auto",      # auto / float32 / bfloat16
}

#: 允许的值域，设置接口按这个校验（别让前端塞个 "gpu" 进来）
ASR_CHOICES = {
    "device": ("auto", "cpu", "cuda:0", "cuda"),
    "dtype": ("auto", "float32", "bfloat16", "float16"),
}

# ---------------- 对齐器（R3） ----------------
ALIGN = {
    # 在当前位置前后各取多少字做 DTW 窗口。
    # 前瞻要盖住「4 秒窗口最多念多少字」+ 一次跳读；回看给念错留修复余地。
    "lookback": 40,
    "lookahead": 100,
    # 低于这个置信度整拍丢弃，位置不动（宁可不动，不要乱跳）
    "min_conf": 0.45,
    # 迟滞：置信度不够高时，不许把位置往回拉超过这么多字
    "back_step_max": 3,
    "back_conf": 0.80,
    # 代价：稿件侧漏字（ASR 没听清）比识别侧多字更常见，所以给得低一点
    "gap_script": 0.55,
    "gap_asr": 0.85,
    # 同声母或同韵母的代价（"是/事"这种，只错一点，不该算串行）
    "cost_near": 0.35,
    "cost_miss": 1.0,
}

# ---------------- ASR ----------------
ASR = {
    "dtype": "auto",      # auto → cuda 上 bf16，cpu 上 float32
    "device": "auto",     # auto → 有 CUDA 用 cuda:0
    "language": "Chinese",
    "max_new_tokens": 256,
    # 每次送进模型的音频长度。太短语义不足、太长延迟高
    "window_sec": 4.0,
    # 每隔多久跑一次识别（不是每次音频块都跑，模型没那么快）。
    # GPU 稳态推理约 0.25 s，所以 0.30 s 一拍 ≈ 3 Hz；CPU 上会自动变成推理瓶颈（约 1 Hz）
    "hop_sec": 0.30,
    # 少于这个时长的静音不送模型
    "min_speech_sec": 0.35,
    # 说话能量门限（RMS），低于它视为静音
    "rms_gate": 0.004,
}
