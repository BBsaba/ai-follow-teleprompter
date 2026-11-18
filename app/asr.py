"""Qwen3-ASR 推理封装。

底层用官方 `qwen-asr` 包（它自带一份 modeling 实现，能绕开 transformers 版本间
`apply_chat_template` / `apply_transcription_request` 与 `torch_compilable_check`
的兼容坑——那几个坑在本项目里逐个踩过，详见 docs 里的 R2 记录）。

为什么不让业务代码直接调 qwen_asr：
  · 加载 1.8 GB 权重很慢，必须懒加载 + 只加载一次；
  · 单卡/单 CPU 要串行，用锁兜住；
  · 要把 device / dtype / 耗时 / RTF 统一成状态字典，前端才有得显示。

`transcribe(context=...)` 是给 R4 留的钩子：把"这篇稿子大概会说什么"当上下文
喂进去，是免费的准确率。R2 先不用。
"""
from __future__ import annotations

import threading
import time

import numpy as np

from . import config, model_finder

SR = 16000


class AsrEngine:
    def __init__(self, model_dir=None, device: str | None = None, dtype: str | None = None):
        # model_pref = 用户的选择（设置页/环境变量设的那个），None = 在 models/ 里按内容自动找；
        # model_dir  = 真正加载成功用上的绝对路径，只读，给状态栏和设置页看。
        # 两者分开是因为「自动找」找到之后不能把结果写回偏好——否则下次比较时
        # 会把"自动"误判成"改成了具体路径"，白白卸载重载一次模型。
        self.model_pref = str(model_dir) if model_dir else config.ASR_MODEL_EXPLICIT
        self.model_dir: str | None = None
        self.want_device = device or config.ASR["device"]
        self.want_dtype = dtype or config.ASR["dtype"]

        self.m = None
        self.device = None
        self.dtype_name = None
        self.load_ms = 0
        self.warmup_ms = 0
        self.last_ms = 0
        self.last_audio_sec = 0.0
        self.error: str | None = None

        self._lock = threading.Lock()   # 单卡串行，别并发抢显存

    # ---------- 加载 ----------
    def load(self) -> None:
        if self.m is not None:
            return
        import torch
        from qwen_asr import Qwen3ASRModel

        t0 = time.perf_counter()

        # 先定位目录。找不到就抛 ModelMissing——文案里直接写清楚「放哪、怎么下」，
        # 而不是让用户去读 from_pretrained 的堆栈猜是路径错了还是文件缺了。
        found, tried = model_finder.find(self.model_pref)
        if found is None:
            raise model_finder.ModelMissing(
                model_finder.explain(tried), model_finder.explain_short())
        self.model_dir = str(found)     # 记下真正用的目录，状态栏里看得见

        dev = self.want_device
        if dev == "auto":
            dev = "cuda:0" if torch.cuda.is_available() else "cpu"

        dt = self.want_dtype
        if dt == "auto":
            dt = torch.bfloat16 if dev.startswith("cuda") else torch.float32
        elif isinstance(dt, str):
            dt = getattr(torch, dt)

        self.m = Qwen3ASRModel.from_pretrained(
            self.model_dir,
            dtype=dt,
            device_map=dev,
            max_new_tokens=int(config.ASR["max_new_tokens"]),
        )
        self.device = dev
        self.dtype_name = str(dt).replace("torch.", "")
        self.load_ms = int((time.perf_counter() - t0) * 1000)
        self.error = None

        # CUDA 上第一次推理要交约 1 秒的"开机费"（kernel 加载 + cuBLAS/cuDNN 初始化）。
        # 不做预热的话，这笔钱会在用户开口说第一句话时扣——表现为"前两秒没反应"。
        # 静音跑两遍即可，输出丢掉。
        self._warmup()

    def reconfigure(self, model_dir=None, device=None, dtype=None) -> bool:
        """应用设置页的新选择；返回是否真的变了。

        **只改参数，不主动加载**——真正的加载还是等用户点「开始」，
        否则一按保存就卡十几秒，界面看着像死了。
        真的变了才把已加载的模型丢掉，下次 load() 按新参数重来；
        没变就什么都不做，避免"保存一下白等 15 秒"。
        """
        new_pref = model_dir or None
        changed = (
            new_pref != self.model_pref
            or (device is not None and device != self.want_device)
            or (dtype is not None and dtype != self.want_dtype)
        )
        self.model_pref = new_pref
        if device is not None:
            self.want_device = device
        if dtype is not None:
            self.want_dtype = dtype
        if changed:
            self.m = None
            self.model_dir = None
            self.device = None
            self.dtype_name = None
            self.load_ms = self.warmup_ms = self.last_ms = 0
            self.last_audio_sec = 0.0
            self.error = None
        return changed

    def _warmup(self, runs: int = 2) -> None:
        try:
            import numpy as np

            buf = np.zeros(SR, dtype=np.float32)   # 1 秒静音
            t0 = time.perf_counter()
            with self._lock:
                for _ in range(runs):
                    self.m.transcribe(audio=(buf, SR), context="", language=None)
            self.warmup_ms = int((time.perf_counter() - t0) * 1000)
        except Exception:
            # 预热失败不影响正常使用，只是第一拍会慢
            self.warmup_ms = 0

    @property
    def ready(self) -> bool:
        return self.m is not None

    def status(self) -> dict:
        return {
            "ready": self.ready,
            "device": self.device,
            "dtype": self.dtype_name,
            "load_ms": self.load_ms,
            "warmup_ms": self.warmup_ms,
            "last_ms": self.last_ms,
            "rtf": round(self.last_ms / 1000 / self.last_audio_sec, 3)
            if self.last_audio_sec else None,
            "model": self.model_dir or str(config.ASR_MODEL),
            "model_pref": self.model_pref,
            "want_device": self.want_device,
            "want_dtype": self.want_dtype,
            "error": self.error,
        }

    # ---------- 推理 ----------
    def transcribe(
        self,
        wav: np.ndarray,
        sr: int = SR,
        language: str | None = None,
        context: str | None = None,
    ) -> str:
        if not self.ready:
            self.load()
        if sr != SR:
            raise ValueError(f"只接受 {SR} Hz，收到 {sr}")

        lang = config.ASR["language"] if language is None else language
        wav = np.ascontiguousarray(wav, dtype=np.float32)

        with self._lock:
            t0 = time.perf_counter()
            res = self.m.transcribe(
                audio=(wav, SR),
                context=context or "",
                language=lang or None,
            )
            self.last_ms = int((time.perf_counter() - t0) * 1000)
            self.last_audio_sec = len(wav) / SR
        return (res[0].text or "").strip()
