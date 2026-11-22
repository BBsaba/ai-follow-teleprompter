# AI 语音跟随提词器（录口播版）· 工程规划 v2.0

> **阅读须知（给从 GitHub 来的读者）**
>
> 这份文档是**开发过程的原始施工图**，按「一个人边做边记」的方式写，没有为公开发布做过改写。读之前请注意四点：
>
> 1. **文中的绝对路径（`D:\AITeleprompter\`、`D:\WorkBuddy\...`）和硬件型号（i5-13400F / RTX 3060 Ti 8 GB）都是开发机的真实环境**，是当时的操作记录，不是要求你也这样配。你按自己的路径和硬件理解原理即可，实际跑请照 `README.md`。
> 2. **文中「R1 / R2 / R3」是内部对三个开发轮次的叫法**（R1 界面、R2 识别、R3 对齐），不是版本号。
> 3. **文中的决策、推翻、自我批评都是真实过程**——包括走错的弯路和被实测否掉的方案。这些恰恰是这份文档最有价值的部分：它记录了「为什么不那么做」。请当**案例**读，不要当**规范**读。
> 4. **与 `README.md` 冲突时，以 `README.md` 为准**。README 是给使用者看的现状说明，本文是历史记录，早期章节里的结论可能已被后面的章节推翻（每次推翻都在「变更记录」里有注记）。

**日期**：2026-11-17
**场景**：R1 界面 / R2 识别 / R3 对齐 已完工；推进方式可切换；AI 模式开始自动开麦并显示运行状态
**参与成员**：主理人（规划与编排）；R1 起按 product-reviewer → 实现 → qa-lead 顺序推进
**目标平台**：Windows 10 本机（i5-13400F / 32 GB / RTX 3060 Ti 8 GB），纯本地推理，不联网
**文档用途**：这是"给自己看的施工图"。下一轮写代码时，所有需要拍板的事情应该已经在这里拍完了，不再重新讨论。
**代码位置**：`D:\AITeleprompter\`（v1.6 起；旧的 `D:\WorkBuddy\projects\ai-teleprompter\` 停用）

### 变更记录

| 版本 | 日期 | 变更内容 |
|---|---|---|
| v1.0 | 2026-11-16 | 初稿：锁定录口播场景、8 轮节奏、拼音两级代价对齐器 |
| v1.1 | 2026-11-16 | 新增字号可调、内置编辑器；断行改为"句块 + CSS 折行" |
| v1.2 | 2026-11-16 | 两态模型（开录即冻结）：删掉调字号锚点补偿与编辑后位置重映射 |
| v1.3 | 2026-11-16 | 新增视觉与操作规格：**红线标尺**、**当前行上下位置可调**、**黑底白字**、**读完变灰**、**滚轮选行**。因红线/按行染色/滚轮选行都以"行"为单位，**断行策略回退为"按字数硬切行"**（推翻 v1.1 的 CSS 自然折行，见 §4.1）；`Script` 接口由 `segments` 改回 `lines`；录制态键盘收敛为**只有空格与 Esc**，原 `Ctrl+R` 手动重锚取消（由滚轮承担） |
| v1.4 | 2026-11-16 | ① 新增 **§4.7 窗口尺寸适配**：任何窗口尺寸下红线都贴当前行底边（含 F11、第二屏、125% 缩放、拖动窗口）；② 明确 **逐行跳变**渲染（行内逐字染色，跨行瞬间平移 + 120 ms 过渡），`Motion` 在逐行模式下退化为低通滤波、不再使用前瞻；③ 红线默认高度按实拍图统一为 **42%**；④ 新增检查项 C6、决策 D-14/D-15 |
| v1.5 | 2026-11-16 | **R1 完工回填**：① 新增 **§4.8 屏边渐隐**（实拍暴露"半截字"硬切，改为按行几何精确算渐隐区）；② 新增 **§4.9 红线高度钳位**（字号拉到上限且红线拖到下限时，当前行会被挤出上边缘，改为钳位保护）；③ 切行阈值 0.55→0.70 + 中文**避头规则**（实拍暴露"："跑到行首、首行只有 9 字）；④ 新增决策 D-16/D-17、风险 R-14/R-15；⑤ §10 改写为「R1 施工结果 + R2 开场清单」 |
| v1.6 | 2026-11-16 | **工程搬迁 + R2 起飞**：① 全部代码与权重移入单根目录 **`D:\AITeleprompter\`**（用户要求"方便打包发给别人或上传开源平台"），路径全相对推导，新增 `README.md`/`.gitignore`/`tools/download_model.py`/`start.bat` 可移植启动；② 权重下载实测（ModelScope 1.75 GB / 47 MB/s）；③ ASR 链路跑通，**CPU RTF 0.30**；④ 新增 **§11 依赖踩坑记录**（transformers 版本、chat_template 不渲染 assistant 轮、mel 帧必须是 100 的倍数、qwen-asr 自带 modeling）；⑤ 新增 **§11.5 打包链路**：`tools/package.py`（code 168 KB / full 1.8 GB 两套产物）+ `setup.bat`，并做了**解压到异地另起服务**的可移植性实测；`PORT` 改读 `TELEPROMPTER_PORT` |
| v1.7 | 2026-11-16 | **R3 完工**：① 装 CUDA 版 torch，实测 GPU 稳态 **251 ms / RTF 0.06**（CPU 1280 ms，5.1×）；② 新增 **§12**：GPU 化与两个测量错误、`app/align.py` 半全局 DTW（0.66 ms）、双驱动切换、**「开麦加载期模拟跑飞」真 bug**、节拍重写、111 项测试、空间清理 7 GB |
| v1.8 | 2026-11-16 | **推进方式开关**：① 自动滚动与 AI 跟随改为**用户显式二选一**（`ui["follow_mode"]`，单一数据源、持久化），删掉 `sim_enabled`/`asr_drive` 三个布尔量的隐式切换；② 切换时对齐器重锚；③ 控制台分段开关，AI 模式下速度滑块置灰；④ 新增 **§13**；测试 **117 项**，统一入口 `python tests/run_all.py` |
| v1.9 | 2026-11-17 | **修「AI 根本不跟随」**：① 根因是 `start` 只改状态、从不碰麦克风（§14.1）；② AI 模式开始自动开麦 + 加载状态可见；③ 控制台新增 AI 运行状态条（四档，§14.3）；④ 新增删除稿件（含路径穿越防护，§14.4）；⑤ 修侧栏 grid 压塌导致模式开关被预览框盖住（§14.5）；测试 **164 项** |
| v2.0 | 2026-11-17 | **设置页 + 模型自动发现**：① 新增 `/settings` 页，麦克风设备可换（含 1.2 秒试音）、语音模型可换、推理 device/dtype 可换，落盘到 `state.json` 的 `asr` 段（§15）；② `app/model_finder.py`：不再认死 `models/Qwen3-ASR-0.6B`，改为**按内容认目录**，文件夹改名/压缩包多套一层/内容直接铺进 `models/` 都能用；③ 找不到模型时给**人话报错**（终端完整说明 + 侧栏两行短提示），不再抛 transformers 堆栈；④ `download_model.py` 承认自己只支持 ModelScope，拦住 HuggingFace 并给出替代命令；⑤ 三个真实缺陷见 §15.4；测试 **265 项** |

---

## TL;DR

- 结论：🟢 可以做，本机硬件处于最优档（8 GB 显存跑 0.6B 非常宽裕）。
- 主场景：**录口播视频**，**黑底白字全屏**，一镜到底，可重录。
- 技术路线：本地 Web UI + Python 推理后端 + 自研拼音对齐器，8 轮交付。
- **v1.3 的核心视觉**：屏幕上有一条**固定的红线**，当前朗读行的底边永远贴着它；念过的字变灰，没念的保持白；滚轮可以手动把"当前行"上下拨动。
- 录制态只认三个输入：**空格暂停/继续，Esc 退出，滚轮拨行**。其余一律拦截。
- 最大的风险仍然是**抖动与跳位**，R3–R5 全部投在算法上。

### 核心结论卡片

| 项目 | 内容 |
|------|------|
| 方案状态 | 🟢 Go（规划定稿，待 R1 开工） |
| 当前版本 | v1.3（红线标尺 + 双级染色 + 滚轮选行） |
| 总轮次 | 8 轮（乐观 6，实际预计 7–9） |
| 关键路径 | R3 对齐器 → R5 平滑 |
| 最大风险 | 中文同音字位置漂移；滚轮与 ASR 抢位置 |
| 验收口径 | 位置误差 ≤ 3 字、反向跳动 ≤ 2 次/分钟、掉队恢复 ≤ 1.5 s |

---

## 1. 产品定义

### 1.1 一句话

**录之前**把稿子粘进去、把字和红线调到舒服的位置；**开录后**只管念——念到哪，哪个字变灰；红线下面永远是接下来要念的。

### 1.2 场景约束

| 维度 | 录口播（本文） | 直播（不做） |
|---|---|---|
| 观看距离 | 0.5–1 m，正对镜头 | 0.8–1.5 m |
| 单行字数 | 8–14 字（大字，减少扫视） | 12–20 字 |
| 屏幕行数 | 3–5 行可见 | 6–10 行 |
| 视觉 | **黑底白字，高对比，无干扰** | 可能叠加画面 |
| 调整时机 | **开录前一次性调好** | 可能边播边调 |
| 关键诉求 | **稳、不抖、重读不跑** | 快、能跳 |

### 1.3 用户故事

1. 我把 800 字稿粘进去，拖滑块把字调到舒服的大小，把红线拖到我眼睛舒服的高度，点开始。
2. 屏幕上黑底白字，我一念，念过的字就变灰，红线下面全是还没有念的。
3. 我念快了 / 念慢了，字跟着我的速度走，不是匀速滚。
4. 我停下来想词 5 秒，它**原地不动**；按空格可以主动暂停，再按继续。
5. 我念错一句、从头重念这一句，它退回去，不跳到别处。
6. 我临时加了一句稿子上没有的话，它**等我说完**，然后回到稿子上继续。
7. 我跳读了一段，**滚一下滚轮**把当前行拨到我要念的那行，上面全灰、这行及下面全白。
8. 我中途走开倒水回来，它能在 1.5 秒内自己找回位置。
9. 我要对着半透镜提词器拍，画面要能水平镜像。
10. 我要把提词窗拖到第二块屏，主屏留给相机预览。
11. 我嫌字号不合适，按 Esc 停下，调大两档，再开始。
12. 我改稿时发现第二段少了一句，在软件里补上，保存，然后开录。

### 1.4 不做什么（范围红线）

- ❌ 不做手机端、不做小程序
- ❌ 不做视频录制、剪辑、字幕导出
- ❌ 不做多人对话剧本、角色分色
- ❌ 不做云同步、账号
- ❌ 不做实时字幕推流给 OBS（留接口）
- ❌ 不做多语言（中文为主 + 中英混排）
- ❌ 不做"AI 改写稿件"
- ❌ 编辑器不做富文本、图片、表格
- ❌ **不做"边录边改"**（见 §1.5）

### 1.5 两态模型：准备态 / 录制态

| 能力 | 准备态（IDLE / EDIT） | 录制态（FOLLOWING / LOST / PAUSED） |
|---|---|---|
| 字号 / 每行字数 / 行距 | ✅ 可调 | 🔒 锁定 |
| **红线高度（当前行位置）** | ✅ 可调 | 🔒 锁定 |
| 文本内容 | ✅ 可编辑 | 🔒 只读 |
| 字体 / 边距 / 颜色 | ✅ 可调 | 🔒 锁定 |
| 镜像 | ✅ 可调 | ✅ 可调（`scaleX(-1)`，不动索引） |
| `空格` | R1 模拟推进（R2 后失效） | ✅ **暂停 / 继续** |
| `Esc` | — | ✅ **退出到准备态** |
| 滚轮 | 普通滚动预览 | ✅ **拨动当前行** |
| 全屏 `F11` | ✅ | ✅ |

**录制态只认三个输入：空格、Esc、滚轮。** 其它键（包括 `Ctrl+=`、`Ctrl+E`、`Ctrl+R`）一律拦截，并小字提示"已锁定，按 Esc 退出后可调"。

> 原 v1.2 的 `Ctrl+R` 手动重锚**已取消**——滚轮选行本来就是更强的手动重锚，功能重叠。自动重锚（LOST 后由 ForcedAligner 触发）保留。

### 1.6 视觉与操作规格（v1.3 新增）

| 项 | 规格 |
|---|---|
| 背景 | 纯黑 `#000000`，不透明，全屏 |
| 未读文字 | 纯白 `#FFFFFF` |
| 已读文字 | 灰 `#7A7A7A`（可调，亮到 `#C8C8C8`） |
| 当前正在念的字 | 白（与未读同色，靠"半行变灰"形成进度感；可选加粗，默认关） |
| **红线** | `#FF2D2D`，**2 px**（可调 1–4 px），横贯屏宽，常驻不动 |
| 红线位置 | 当前朗读行的**底边**贴在红线**上方 8 px**处（间隙可调） |
| 红线高度（可调） | 屏高 **15%–70%**，默认 **42%**，准备态用滑块调；**随窗口尺寸实时重算**（§4.7） |
| 窗口适配 | 任意窗口尺寸 / F11 / 第二屏 / 系统 125% 缩放：红线始终贴当前行底边（误差 ≤ 2 px），字号上限自动收紧 |
| 暂停反馈 | 红线由红变灰 `#8A8A8A`，恢复即变红（默认开启） |
| 行结构 | 每行 ≤ 14 字（可调 8–20），硬切行，不靠浏览器折行 |
| 字体 | 思源黑体 / 微软雅黑 Bold，字号 24–160 px（上限受屏宽约束） |

---

## 2. 成功标准

### 2.1 录制态指标

| # | 指标 | 目标 | 测量方式 |
|---|---|---|---|
| M1 | 位置误差（中位） | ≤ 3 字 | 人工标 5 个锚点/段，比对 |
| M2 | 反向跳动 | ≤ 2 次/分钟 | 日志统计 `pos` 回退事件 |
| M3 | 掉队恢复时间 | ≤ 1.5 s | LOST → FOLLOWING 时长 |
| M4 | 端到端延迟 | ≤ 400 ms | 说话到字变灰的时间差（录屏逐帧） |
| M5 | 停顿误滚 | 0 次 | 静音 5 s，位置不动 |
| M6 | 稳定运行 | 60 分钟不崩、内存不涨 | 长跑 + 内存曲线 |
| M7 | 启动到可念 | ≤ 15 s（模型已缓存） | 秒表 |
| M8 | GPU 显存占用 | ≤ 4 GB | nvidia-smi |

### 2.2 准备态与交互检查项

| # | 检查项 | 通过标准 |
|---|---|---|
| C1 | 字号连续拖动 | 24 → 屏宽上限，无横向溢出、无错行，重启后仍生效 |
| C2 | 大稿粘贴与保存 | 粘贴 3000 字渲染 < 100 ms；800 ms 后自动保存；`Ctrl+S` 后开始从**第 1 字**起 |
| C3 | 模式锁定 | 录制中按 `Ctrl+=` / `Ctrl+E` 无效并提示；只有空格 / Esc / 滚轮有效 |
| C4 | 红线高度可调 | 15%–70% 连续拖动，红线始终贴当前行底边（误差 ≤ 2 px），重启后保留 |
| C5 | 滚轮选行染色 | 向上/向下各拨 5 行：被选行以上**全灰**、被选行及以下**全白**、红线随行移动 |
| C6 | 窗口尺寸适配 | 窗口从 1920×1080 拖到 960×540、再 F11 全屏、再拖到第二屏：红线始终贴当前行底边（误差 ≤ 2 px），字不溢出、不闪烁 |
| **C7** | **屏边无半截字**（v1.5） | 任何字号 × 任何红线位置：窗口上下边缘要么是完整行，要么是渐隐，不出现被横切的半排字 |
| **C8** | **极端参数不失效**（v1.5） | 字号 160 + 红线 15%：当前读的那一行仍**完整可见**（允许红线被钳位到 18%） |
| **C9** | **中文避头**（v1.5） | 任意稿件切行后，**没有任何一行以收尾标点开头**；且不丢字（拼接结果 = 原文） |

---

## 3. 系统架构

### 3.1 部署形态

```
┌─────────────────────────────────────────────┐
│ 浏览器 / pywebview 窗口（前端，纯 JS）        │
│  - 提词窗（黑底 / 红线 / 镜像 / 第二屏）      │
│  - 控制台（编辑稿、调字号、调红线高度）       │
└───────────────▲─────────────────────────────┘
                │ WebSocket（30–60 Hz 推送行号与行内进度）
┌───────────────┴─────────────────────────────┐
│ Python 后端（FastAPI + uvicorn）             │
│  audio → asr → align → motion                │
│  script（预处理/重建） · reanchor（自动旁路） │
└─────────────────────────────────────────────┘
```

- 绑定 `127.0.0.1:8756`，不对外暴露，无鉴权。
- 前端零构建，改一行刷新即见。
- R7 用 pywebview 套壳，代码零改动。

### 3.2 数据流时序

```
t=0       麦克风 16 kHz / 20 ms 帧 → 环形缓冲（30 s）
t=+0      VAD 判静音 → 不计入 ASR，不推进
t=+600ms  ASR worker 取 600 ms 音频块 → partial 文本（跨块滑动窗口 12 s）
t=+605ms  Aligner 拼音 + 局部 DTW → (pos, conf)
t=+606ms  Motion 速度估计 + 前瞻 + 迟滞 → display_pos
t=+608ms  WS 推送 {line, readIdx, conf} → 前端：行级染色 + 文本平移
```

关键：**ASR 出字慢没关系**，`Motion` 补 1–4 字前瞻，与延迟互相抵消。

### 3.3 工程目录

代码放 `D:\WorkBuddy\projects\ai-teleprompter\`。

```
ai-teleprompter/
├─ run.py
├─ requirements.txt
├─ README.md
├─ app/
│  ├─ server.py            # FastAPI：静态文件 + /ws + /api/*
│  ├─ config.py            # 全部常量（见 3.5）
│  ├─ scripts.py           # 稿件读写
│  ├─ audio.py             # 采集、VAD、环形缓冲
│  ├─ asr.py               # Qwen3-ASR 封装（懒加载、可暂停）
│  ├─ align.py             # 拼音索引 + 半全局 DTW
│  ├─ motion.py            # 平滑 / 前瞻 / 迟滞
│  ├─ reanchor.py          # ForcedAligner（LOST 自动触发）
│  ├─ script.py            # 稿子解析、硬切行、注音、数字读法
│  └─ state.py             # 状态机 + 两态锁定
├─ web/
│  ├─ prompter.html        # 提词窗
│  ├─ console.html         # 控制台（左编辑 / 右预览）
│  ├─ editor.js
│  ├─ render.js            # 逐字 span + 行级染色 + 红线
│  ├─ main.js              # WS、位置插值、滚轮、快捷键
│  └─ style.css
├─ data/
│  ├─ scripts/
│  └─ state.json           # 字号、每行字数、镜像、红线高度、last_script_id
└─ tests/
   ├─ test_align.py
   ├─ test_motion.py
   ├─ test_script.py       # 切行、注音、数字读法
   └─ eval/
```

### 3.4 模块接口

```python
# app/script.py
@dataclass
class Char:
    idx: int
    ch: str
    py: tuple[str, str]      # (声母, 韵母)
    is_punct: bool
    line: int                # 所属行（v1.3 回归，见 §4.1）

class Script:
    text: str
    chars: list[Char]
    lines: list[tuple[int, int]]        # 每行 [start_idx, end_idx)，≤ per_line 字
    @classmethod
    def from_text(cls, text: str, per_line: int = 14) -> "Script"
    def pinyin_window(self, lo: int, hi: int) -> list[tuple[str, str]]
    def line_of(self, pos: int) -> int          # 字索引 → 行号
    def line_start(self, line: int) -> int      # 行号 → 首字索引

# app/align.py
class Aligner:
    def __init__(self, script: Script)
    def update(self, asr_text: str) -> AlignResult
    def reset(self, pos: int = 0) -> None

# app/motion.py
class Motion:
    def step(self, pos: int, conf: float, dt: float) -> float   # display_pos
    def snap(self, pos: int) -> None            # 滚轮选行后瞬间对齐，不做缓动
    def freeze(self) -> None

# app/asr.py
class StreamingASR:
    def start(self) -> None
    def push(self, pcm: np.ndarray) -> str | None
    def pause(self) -> None      # 停止消费并丢弃暂停期间音频
    def resume(self) -> None
    def stop(self) -> None
```

**HTTP / WS 接口**

```
GET  /api/scripts                 → [{id, title, chars, est_sec, mtime}]
POST /api/scripts                 → body {id?, text, title?} → {id, chars, est_sec}
GET  /api/scripts/{id}            → {id, text}
GET  /api/state  /  PUT /api/state → {font_px, per_line, mirror, cue_ratio, read_color, last_script_id}

WS   /ws
  服务端 → 前端：{type:"pos", line:int, readIdx:int, conf, paused:bool}
                {type:"state", s:"IDLE|LISTENING|FOLLOWING|LOST|REANCHOR|PAUSED"}
  前端 → 服务端：{type:"start"|"stop"|"pause"|"resume"}
                {type:"wheel", delta:int}    # ±1 行，仅录制态
                {type:"edited", text}        # 仅 IDLE 允许
```

> `pos` 不再直接下发浮点字索引，而是下发 **行号 + 行内已读字数**。渲染的最小单位是"行"，让前端自己折算容易和后端算法错位。

### 3.5 关键常量（config.py）

```python
AUDIO   = dict(sr=16000, frame_ms=20, ring_sec=30, vad_aggr=2)
ASR     = dict(model="Qwen/Qwen3-ASR-0.6B", chunk_ms=600, max_chunk_ms=2000,
               context_sec=12, device="cuda", dtype="bfloat16")
ALIGN   = dict(lookback=24, lookahead=140, min_match=6, min_conf=0.45,
               penalty_same_initial=0.35, penalty_same_final=0.35, penalty_miss=1.0)
MOTION  = dict(lead_sec=0.35, lead_min=1.0, lead_max=4.0,
               tau_fwd=0.09, tau_back=0.22, freeze_speed=0.4)
UI      = dict(per_line=14, per_line_min=8, per_line_max=20,
               font_px=64, font_min=24, font_max=160, font_step=2,
               line_height=1.9, max_visible_rows=5,
               cue_ratio=0.38, cue_ratio_min=0.15, cue_ratio_max=0.70,
               cue_gap_px=8, cue_thickness=2,
               bg="#000000", fg="#FFFFFF", read="#7A7A7A",
               cue="#FF2D2D", cue_paused="#8A8A8A", mirror=False)
WHEEL   = dict(cooldown_ms=800, min_conf_during_cooldown=0.80)
EDITOR  = dict(autosave_ms=800, max_chars=20000)
```

---

## 4. 关键算法

### 4.1 切行策略（v1.3 反转：从 CSS 折行改回硬切行）

v1.1 曾把折行交给浏览器（为了"调字号版式稳定"）。v1.3 必须改回来，原因是出现了三个**以"行"为单位**的硬需求：

| 需求 | 为什么 CSS 折行做不到 |
|---|---|
| 红线贴在"当前行"底部 | 浏览器折行后前端不知道"当前行"是哪几个字、底边在哪（只能靠 `Range.getClientRects()` 反推，脆弱） |
| 滚轮按行上下拨 | 没有显式行索引就没法"±1 行" |
| 被选行以上全灰、以下全白 | 需要行级染色，`<div class="line">` 是最自然的单位 |

所以：**每行 ≤ `per_line` 个字，硬切成 `<div class="line">`，行宽 = 字号 × (per_line + 1.2)，居中对齐。**

> **1.2 是"避头溢字"的余量**（见下）。v1.3 时写的是 `× 1.03`，实拍发现避头回拉会让某行多出 1–2 个字，`1.03` 直接溢出换行，把 `white-space: nowrap` 撑破。

中文等宽，14 字正好占满；行宽随字号等比缩放，版式仍然稳定（v1.1 想要的"调字号不换版式"依旧成立，只是实现手段换了）。
英文单词可能被切断，口播稿里英文比例低，可接受；必要时按空格优先断（P2）。

**两条切行规则是实拍改出来的**（v1.5，都有单测锁住）：

1. **标点优先阈值 = 行长的 70%**。原先是 55%，结果"大家好，我是老张。"只有 9 个字就独占一行，右边空掉三分之一。现在只在**行尾 30%** 范围内找标点，找不到就硬切。
2. **避头规则**：行首**不允许**出现收尾标点（`，。！？；：、）》”’…` 等）。中文排版铁律，破掉以后屏幕上会出现一行以"："开头的字——非常刺眼。

```python
NO_LINE_START = set("，。！？；：、）》〉”’…·,.!?;:)]}")

floor = max(1, int(per_line * 0.70))       # 只在此之后的标点才值得为它断行
...
# 避头：行首的收尾标点拉回上一行（允许溢出 1 个字，由 CSS 余量吸收）
for k in range(1, len(lines)):
    while lines[k] and lines[k][0] in NO_LINE_START and len(lines[k-1]) < per_line + 1:
        lines[k-1] += lines[k][0]
        lines[k] = lines[k][1:]
```

预处理步骤：

1. 去空行、合并硬换行（`Shift+Enter` 的强制换行标记优先断行）；
2. 按标点优先断句，再按 `per_line` 硬切；
3. **避头回拉**（把行首标点塞回上一行）；
4. 逐字转拼音（pypinyin + 多音字词典；数字/百分比/英文按读法展开）；
5. 生成 `chars` 与 `lines`。

### 4.2 受限对齐（核心，20 行）

```python
def update(self, asr_text: str) -> AlignResult:
    q = to_pinyin_tokens(asr_text)
    if len(q) < 2:
        return self.last

    lo = max(0, self.pos - LOOKBACK)
    hi = min(len(script), self.pos + LOOKAHEAD)
    P  = script.pinyin_window(lo, hi)

    score, end = semiglobal_dtw(P, q)       # q 整体匹配；P 两端可自由空转
    conf = 1.0 - score / (len(q) * PENALTY_MISS)

    if conf < MIN_CONF:
        return AlignResult(self.pos, conf, 0)

    new_pos = lo + end
    if new_pos < self.pos - 3 and conf < 0.80:   # 迟滞
        new_pos = self.pos
    return AlignResult(new_pos, conf, new_pos - self.pos)
```

代价函数用**声母/韵母两级惩罚**：

| 情况 | 代价 |
|---|---|
| 完全相同 | 0 |
| 同声母不同韵母（"是" vs "事"） | 0.35 |
| 同韵母不同声母（"字" vs "次"） | 0.35 |
| 完全不同 | 1.0 |

ASR 把"是"听成"事"，代价只有 0.35，不足以触发跳位——**这是中文提词器必须走拼音的原因**。

半全局 DTW：DP 第一行全 0（起点自由），取最后一列最小值的位置作终点。窗口 164 × 20 ≈ 3k 格，< 2 ms。

### 4.3 位置平滑（逐行模式下退化为低通滤波）

**先纠正一个认知**：v1.0–v1.3 一直写"前瞻 1–4 字"，那是**连续滚动**提词器的做法。v1.3 定了逐行跳变（红线永远贴当前行底边），前瞻就失效了——**行是离散单位，没法"提前半行"**。硬加前瞻会让下一行提前变成"当前行"，而用户还在念上一行最后几个字。

所以逐行模式下 `Motion` 只干一件事：**把跳变磨平，别在行边界来回抽搐**。

```python
inst = clamp((pos - self.prev) / dt, -40, 40)   # 瞬时字/秒
self.v = 0.8 * self.v + 0.2 * inst
tau  = TAU_BACK if pos < self.d else TAU_FWD     # 前进 90 ms / 后退 220 ms
self.d += (pos - self.d) * (1 - math.exp(-dt / tau))
```

- **前进快、后退黏**：念快了能追上，念错了不弹回去；
- **不做前瞻**：`lead_sec` 参数保留，只在未来的"连续滚动模式"里启用；
- **行边界不额外加阻尼**：靠上游的 `min_conf` 与迟滞保证不抖，渲染层不要二次加工，否则会迟滞叠加。

> 结论：R5 要调的其实是三个数（τ 前进 / τ 后退 / 冻结阈值），不是一个曲线。

### 4.4 状态机

```
IDLE ──点开始/空格──▶ LISTENING ──conf≥0.45 ×2──▶ FOLLOWING
                                               │  ↕ 空格
                                            PAUSED
  ▲                                            │
  │                                 1.5 s 无有效匹配
  │                                            ▼
  │                                        LOST ──▶ REANCHOR（自动）──▶ FOLLOWING
  └──────────────── Esc ───────────────────────┘
```

- **PAUSED**：空格触发。`asr.pause()`，丢弃暂停期间音频；红线转灰。滚轮仍可用（暂停正是调整的好时机）。
- **LOST**：位置冻结在最后可信点，小字提示"正在重新定位"。
- **REANCHOR（自动）**：取最近 6 s 音频 + 稿子 `pos±2 行`，调 ForcedAligner-0.6B，取最高分位置一次跳过去。
- **Esc**：停止，回 IDLE，解锁全部准备态设置。

### 4.5 渲染：红线 + 双级染色（v1.3 核心）

**红线是固定标尺，文本在它下面滑。** 这是最省事也最稳的做法——红线永远不动，动的是文字。

```
红线 y = cue_ratio × 屏高                       （常驻，绝对定位）
当前行底边目标 y = 红线 y − cue_gap             （默认 8 px）
文本层 translateY = 目标y − (lines[cur].offsetTop + 行高)
```

每帧只需更新一个 `translateY`，没有重排，稳定 60 fps。

**染色分两级**：

| 层级 | 规则 | 实现 |
|---|---|---|
| 行级 | `line < cur` → 整行灰；`line > cur` → 整行白 | `.line.read` 类切换 |
| 字级 | 当前行内，`idx < readIdx` → 灰，其余白 | 当前行的 span 逐个加 `.read` |

滚轮落行时，被选行及以下**整行整行地恢复成白**——这正是"选择后上面行的字全部变灰，被选择行及以下全部变白"。ASR 接着从该行首字开始，行内再逐字变灰。

```js
function applyPos(line, readIdx) {
  const el = lineEls[line];
  const target = cueY() - CUE_GAP - (el.offsetTop + LINE_H);
  layer.style.transform = `translateY(${target}px)`;

  for (let i = 0; i < lineEls.length; i++)
    lineEls[i].classList.toggle('read', i < line);      // 行级
  const chars = lineEls[line].children;
  for (let i = 0; i < chars.length; i++)
    chars[i].classList.toggle('read', i < readIdx);     // 字级
}
```

**暂停反馈**：`PAUSED` 时红线 `stroke` 由 `#FF2D2D` 变 `#8A8A8A`。不闪、不弹窗，余光就能看见。

**准备态**：红线同样显示（预览用），滑块调 `cue_ratio` 时红线实时上下移动，文字跟着走——所见即所得。

### 4.6 滚轮选行与 ASR 的冲突处理（v1.3 新增）

滚轮是录制态唯一允许的手动干预，但它会和 ASR 抢位置。处理分三步：

```python
def on_wheel(delta):            # delta = ±1
    if state not in (FOLLOWING, PAUSED, LOST):
        return
    new_line = clamp(cur_line - delta, 0, len(lines) - 1)
    start    = script.line_start(new_line)
    aligner.reset(start)        # 对齐器锚点一起挪
    motion.snap(start)          # 显示层瞬间对齐，不做缓动
    wheel_cooldown = now() + 800ms
```

1. **对齐器一起重置**：只移动显示不移动 `aligner.pos`，下一次 ASR 更新会立刻把位置拉回去，用户会觉得"滚了没用"。
2. **800 ms 冷却期**：这期间 ASR 更新只有 `conf ≥ 0.8` 才被接受。滚轮那一刻 ASR 手里的 partial 还是上一句话，匹配到新位置必然低分。
3. **不做缓动**：滚轮是"我要跳"，`snap()` 直接落位，做平滑反而像抽筋。

滚轮一格 = 一行（不是一像素）。触控板高频事件用 16 ms 节流 + 50 ms 去抖，避免一下拨三行。

### 4.7 窗口尺寸适配（v1.4 新增）

提词窗会被拖到第二屏、会 F11 全屏、会被拖小看效果，还可能遇上 Windows 125% 缩放。任何尺寸变化都不能让红线"脱靶"。

**一切尺寸都从两个数推出来**，不写死任何像素：

```js
红线 y      = clamp(stage.clientHeight × cue_ratio, 行高 + gap, 高 − gap)   // 每次 resize 重算
行高        = fontSize × line_height
字号上限    = floor(stage.clientWidth × 0.96 / (per_line + 1.2))
生效字号    = min(用户设定, 字号上限)
文本 translateY = 红线 y − cue_gap − (当前行 offsetTop + 行高)
```

四条纪律：

1. **红线位置由 JS 写入 px**（`cueEl.style.top = cueY()`），写进 `relayout()` 同一个函数里——因为红线 y 同时决定"文本要平移多少"，**两处必须用同一个数**。早期版本让 CSS 用 `calc(var(--cue)*100%)` 自己算、JS 又按 `cue_ratio` 另算一遍，一旦加了钳位（§4.9）两边就会分叉，红线立刻脱离行底。**同一个量只能有一个来源。**
2. **resize 只重算 `translateY` 与红线 y**，不重建 DOM。`ResizeObserver` 监听 stage，`requestAnimationFrame` 合并，一帧最多一次。
3. **resize 时临时关掉 120 ms 过渡**：否则拖动窗口的每一帧都在做动画，画面会"追不上"，看起来像抽筋。做法是加 `.no-anim` 类，两帧后移除。
4. **字号随窗口收紧**：窗口变窄时生效字号自动降，但**用户设定的值不改**（变回来还能恢复）。控制台显示"实际字号被预览宽度限制为 N px"。

另外两个易漏的点：

- **F11 / 全屏切换**会触发 `resize`，但要额外监听 `fullscreenchange`，因为部分浏览器在切换瞬间 `clientHeight` 还没更新，需要 `setTimeout(…, 50)` 补一次。
- **第二屏**分辨率不同：每个窗口算自己的 `clientHeight`，不要从 console 窗口算——所以设置里存的是**比例**（`cue_ratio`），不是像素值。这也是为什么从头到尾都用比例。

> 实测四个尺寸（960×540 / 1280×720 / 1600×900 / 720×900 竖屏）红线全部落在 42.0%，左右始终居中，无横向溢出。字号按宽度自动降：1280→64(封顶)、960→60、720→45。
> 验收：C6。

---

### 4.8 屏边渐隐（v1.5 新增，实拍暴露的问题）

R1 第一版实拍暴露一个视觉缺陷：**窗口上下边缘会出现"半截字"**。因为行高固定、红线位置固定，屏幕底边必然从某一行的中间切过去，留下半排被横切的巨大汉字——用户第一眼会把它当成渲染 bug。

❌ 试过的两种错做法：

| 做法 | 为什么不行 |
|---|---|
| 加固定高度的边缘渐变（如 `0.6 × 字号`） | 切掉的高度取决于几何关系，固定值有时候盖不住（还是露半截），有时候盖过头（把完整行也压暗） |
| 让文本只滚到"整行边界" | 红线位置是用户可调的，窗口高度是任意的，两者一除根本除不尽，做不到 |

✅ 正解：**渐隐区高度按行几何精确算出来，只盖住"被屏边切开的那一行"，整行一个字都不碰。**

```js
const mod = (a, b) => ((a % b) + b) % b;     // JS 的 % 对负数返回负值，必须自己修正

// 上方：第 0 行的顶若在屏外（top0 < 0），渐隐高度 = 它落到 [0, 行高) 的余数
const top0 = curTop - curLine * lineH;
fadeTop = top0 < 0 ? mod(top0, lineH) : 0;

// 下方：当前行底往下，先数完整行，剩下的那截就是渐隐区
const rest = stageH - curBot;
fadeBot = mod(rest, lineH);
```

两个渐隐层是 `#fade-top` / `#fade-bot`，`z-index` 压在文字之上、红线之下：

```css
#fade-bot { bottom: 0; height: var(--fadeB); 
            background: linear-gradient(to top, var(--bg) 55%, transparent 100%); }
```

**为什么能盖干净**：被切的那一行，其可见部分落在渐隐区的下半段（`≥55%` 处），那里已经是 100% 背景色；渐隐区顶端刚好等于完整行的底边，所以完整行一点不受影响。视觉上表现为"下一行从黑里浮出来"，比硬切自然。

⚠️ 关键前提：渐隐用的是 `var(--bg)`，**背景必须是不透明的纯色**。以后若要做半透明/图片背景，这招失效，得改用 `mask-image`。

---

### 4.9 红线高度钳位（v1.5 新增）

`cue_ratio` 允许 0.15–0.70，字号允许到 160 px。两者一叠加会出事：**红线拖到 0.15、字号 160 时，行高 304 px，而红线在 720 高的窗口上只有 108 px——当前读的那一行整个被顶出屏幕上方。**

```js
function cueY() {
  const want = stage.clientHeight * UI.cue_ratio;
  const hi = Math.max(1, stage.clientHeight - UI.cue_gap_px);
  const lo = Math.min(lineH() + UI.cue_gap_px, hi);   // 保证当前行顶 >= 0
  return clamp(want, lo, hi);
}
```

代价：极端参数下滑块值会与实际红线位置不一致（滑到 15% 但红线停在 18%）。这是**故意的降级**——宁可位置不听滑块，也不能让用户看不见正在读的那一行。

> 决策见 D-17。验收：C6 追加一项"字号 160 + 红线 15% 时当前行仍完整可见"。

---

## 5. 技术选型与被否方案

| 层 | 选择 | 理由 | 被否方案及原因 |
|---|---|---|---|
| 前端 | 原生 JS + CSS transform | 零构建、秒改 | React：构建链拖慢迭代；Qt：动效难写 |
| 后端 | Python + FastAPI + WebSocket | 与推理同语言、零 IPC | Rust/Tauri：编译等待吃掉迭代速度 |
| 编辑器 | textarea + 独立只读预览 | 中文输入法零坑、原生 undo | contenteditable：`composition` 会打断 DOM 与光标 |
| ASR | Qwen3-ASR-0.6B @ CUDA | 中文 SOTA、原生流式、Apache 2.0 | vLLM：Windows 原生不支持；sherpa-onnx：留作 CPU 兜底 |
| 对齐 | 自研拼音半全局 DTW | 稿子已知，最可靠且最便宜（<2 ms） | 端到端 LLM 对齐：慢、不可控、会幻觉 |
| 重锚 | Qwen3-ForcedAligner-0.6B | RTF≈0.001、字级时间戳 | 全稿重扫：慢且没必要 |
| **排版** | **硬切行（`<div class="line">`）** | 红线、按行染色、滚轮选行都需要显式行 | CSS 自然折行：拿不到行边界（v1.1 已推翻） |
| **红线** | **固定标尺 + 文本平移** | 每帧只改一个 `translateY`，无重排 | 红线跟着文字走：需每帧重算行底边，抖 |
| 通信 | WebSocket | 双向、可推送控制 | SSE：控制指令还得另开 REST |

---

## 6. 八轮里程碑

| 轮 | 目标 | 交付物 | 你的验收动作 | 状态 |
|---|---|---|---|---|
| **R1** | 壳 + 编辑器 + 渲染 + 红线 + 滚轮，**不碰模型** | `run.py`、`server.py`、`script.py`、`session.py`、`motion.py`、`store.py`、`prompter.{html,css,js}`、`console.{html,css,js}`、3 个测试文件；空格模拟推进 | ① 粘稿 → 调字号 → 调红线高度 → 空格推进，看灰/白切换是否跟手；② 滚轮上下拨，看"以上全灰、以下全白"；③ 改稿保存 → 开始是否从第 1 字起；④ 录制中按其它键是否被拦 | ✅ **完工**（63 项自动化测试全绿） |
| **R2** | 接麦克风 + ASR | `audio.py`、`asr.py`；页面显示"最近识别到的 20 字" | 说 30 s，看识别文本对不对、延迟多少 | ✅ **完工**（CUDA 稳态 251 ms / RTF 0.06；开麦 11 s 起引擎） |
| **R3** | 对齐器（可离线测） | `align.py` + 5 类单测（正确/漏字/多字/同音/跳句） | `run_all.py` 全绿 + 对着真稿读 3 分钟 | ✅ **完工**（对齐 0.66 ms；位置更新 3.1 Hz）+ §13 推进方式开关 |
| **R4** | 抗错 | 置信度门限、窗口约束、多音字词典、数字读法 | 故意念错同音字、念错整句，位置不跑 | 🟡 **部分**：AI 模式自动开麦 + 运行状态提示 + 删除稿件已做（§14）；抗错本体未动 |
| **R5** | 平滑 | `motion.py`；控制台加实时调参面板（τ / 冻结阈值） | 正常/快/慢/长停顿 四种读法各 1 分钟，数跳动次数 | 待开工 |
| **R6** | 自动重锚 + 滚轮冲突 | `reanchor.py`、LOST 状态、`WHEEL.cooldown_ms` | 卡壳 5 s、跳一段、滚轮拨 10 行，看是否抢位置 | 待开工 |
| **R7** | 打包与体验 | pywebview 套壳或 exe；设置持久化；第二屏；快捷键总表；镜像预设 | 双击启动，当日常工具用一天 | 待开工 |
| **R8** | 评测与固化 | 30 段语料跑分脚本 + 报告；默认参数固化 | 看 M1–M8 与 C1–C5 是否达标 | 待开工 |

**R1 实际耗时落在预估内**（一次会话），返工点只有排版细节（切行阈值、避头、屏边半截字），架构一行没改——说明 v1.2 的"两态模型"与 v1.3 的"硬切行"两个大头决策是对的。

**合计约 6.5 小时净工作时间**，分布在 8 次会话；实际日历跨度取决于你验证的节奏。

### 快捷键总表

| 键 | 阶段 | 作用 |
|---|---|---|
| `空格` | 录制态 | **暂停 / 继续** |
| `Esc` | 录制态 | **退出到准备态** |
| **滚轮** | 录制态 | **当前行 ±1 行** |
| `Ctrl + =` / `-` / `0` | 准备态 | 字号 ±2 / 复位 |
| `Ctrl + 滚轮` | 准备态 | 字号连续调 |
| `Ctrl + E` | 准备态 | 切编辑 / 预览 |
| `Ctrl + S` | 准备态 | 保存并重建 |
| `Ctrl + Z` / `Y` | 编辑 | 撤销 / 重做 |
| `F11` | 任意 | 全屏 |
| `M` | 任意 | 镜像 |

> 录制态按准备态快捷键会被拦截并提示——这条权限边界本身就是防 bug 的机制。

---

## 7. 评测方案（R8 执行，语料从 R3 开始攒）

**语料构成（30 段 × 60–120 秒）**

| 类别 | 段数 |
|---|---|
| 正常语速 | 6 |
| 快语速（≈1.3×） | 5 |
| 慢语速 / 多停顿 | 5 |
| 卡壳重读 | 4 |
| 跳段 / 即兴加词 | 4 |
| 噪声（键盘、空调、翻纸） | 3 |
| 口音（非标准普通话） | 3 |

**流程**：录屏 → 每段人工标 5 个锚点 → 脚本比对 `pos` 日志 → 输出 M1–M8；C1–C5 手工过一遍。

**判据**：M1–M5 + C1–C5 全绿才算"敢用来录课"。

---

## 8. 风险登记册

| # | 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|---|
| R-01 | 中文同音字导致位置漂移 | 高 | 高 | 拼音两级代价 + 迟滞 + 窗口约束（§4.2） |
| R-02 | 流式每块重编码全量音频，长稿 O(n²) | 高 | 高 | 12 s 滑窗，必要时切因果模式 |
| R-03 | 环境噪声被当成语音 | 中 | 中 | VAD + 置信度双门限 + 冻结 |
| R-04 | 抖动（视觉反复横跳） | 高 | 高 | 非对称 τ + 反向需 2× 证据 |
| R-05 | 显存不足 / 与 OBS 抢占 | 低 | 中 | 0.6B 仅 1.6 GB；可切 INT8 或降级 CTC |
| R-06 | 需求漂移 | 高 | 中 | §1.4 红线 + §1.5 两态模型 |
| R-07 | 8 轮拖成 20 轮 | 中 | 中 | 每轮必须有可见产出 |
| R-08 | 模型许可变更 | 低 | 低 | Apache 2.0，锁版本 |
| R-09 | 录制中误触改稿/改字号 | 中 | 高 | 两态锁定 + 快捷键拦截 |
| **R-11** | **滚轮选行后 ASR 立刻把位置拉回** | 高 | 中 | 对齐器同步 `reset` + 800 ms 冷却 + `snap` 无缓动（§4.6） |
| **R-12** | 硬切行把英文单词/数字切断 | 中 | 低 | 优先在空格处断；口播稿英文占比低，接受 |
| **R-13** | 红线与文字重叠遮挡 | 低 | 中 | `cue_gap_px` 可调；红线画在文字层之上但留 8 px 间隙 |
| **R-14** | **屏边出现"半截字"，像渲染 bug** | 已发生 | 低 | §4.8 按行几何精确算渐隐区；**前提是背景为不透明纯色** |
| **R-15** | **字号拉满 + 红线拖到底，当前行被挤出屏幕上边缘** | 已发生 | 高 | §4.9 `cueY()` 钳位；代价是极端参数下滑块值与实际位置不一致（故意） |
| **R-16** | 控制台与提词窗各算一遍红线 y，钳位后两边分叉 | 已发生 | 高 | **同一个量只能有一个来源**：`cueY()` 算一次，`relayout()` 同时写文本 `translateY` 与 `cue.style.top` |
| **R-17** | **关提词窗时控制台窗口刷一屏 `ConnectionResetError` Traceback，用户以为崩了** | 已发生 | 中 | 客户端硬断连时 `ProactorEventLoop` 会给已重置的 socket 做 `shutdown` 而抛错，与服务本身无关。在 `lifespan` 里 `loop.set_exception_handler(_quiet_disconnect)` 吞掉 `ConnectionResetError / ConnectionAbortedError / BrokenPipeError / winerror 10054,995`，其余照常抛给默认处理器。**注意：吞异常有风险，必须白名单式判断，不能写成 `except Exception: pass`** |

---

## 9. 决策记录（ADR）

| # | 决策 | 理由 | 何时可推翻 |
|---|---|---|---|
| D-01 | 首发只做 Windows 本机 | 用户机器性能够、场景在电脑前 | 要手机拍时（不在 v1） |
| D-02 | 前端零构建 | 迭代速度 > 工程规范 | 需要复杂状态管理时 |
| D-03 | 对齐器自研，不用 LLM | 稿子已知，DTW 更准更快 | 需要语义级跳读理解时 |
| D-04 | R1–R3 不引入 LLM 预处理 | 减少早期依赖 | R4 效果不够时 |
| D-05 | 停顿必须冻结 | 录口播多滚一格即废 | 直播场景另说 |
| D-06 | 8 轮节奏，接口先定死 | 减少返工 | 出现架构级缺陷时 |
| D-07 | 编辑器用 textarea | 中文输入法 composition 会打断 DOM | 需要行内样式高亮时 |
| D-09 | 开录即冻结 | 一次消掉两套补偿算法与两类 bug | 明确要做直播边播边调时 |
| D-10 | 改稿即重置到第 1 字，不做位置重映射 | 排练后改稿属低频，不值得引入算法 | 用户强烈要求时（R7 后） |
| **D-11** | **硬切行，不用 CSS 自然折行** | 红线/按行染色/滚轮选行都需要显式行边界 | 出现超长英文段落时再考虑混排 |
| **D-12** | **红线固定、文本平移** | 每帧只改一个 `translateY`，无重排，稳 60 fps | 需要多条标尺线时 |
| **D-13** | **录制态只留空格 / Esc / 滚轮** | 减少误触；滚轮已覆盖手动重锚能力 | 用户要求恢复 `Ctrl+R` 时 |
| **D-14** | **逐行跳变，不做连续滚动** | 红线要"永远贴在当前行底边"，连续滚动时行底边一直在动，红线就失效了 | 用户改口要"平滑滚动 + 箭头指示"时 |
| **D-15** | **尺寸全用比例，不存像素** | 第二屏、F11、125% 缩放都要自适应；存像素必然脱靶 | 出现固定分辨率的专用提词硬件时 |
| **D-16** | **屏边渐隐按行几何精算，不用固定高度** | 固定值有时盖不住、有时盖过头；精算能保证"整行不碰、半行盖净" | 背景改成半透明/图片时（须改用 `mask-image`） |
| **D-17** | **红线 y 钳位，宁可位置不听滑块** | 看不见正在读的字 = 功能失效；位置偏差只是体验瑕疵 | 字号/红线取值域收窄到几何上必然安全时 |
| **D-18** | **避头规则与标点优先阈值 70% 写进切行器并加单测** | 这两条是"排版是否专业"的肉眼分水岭，靠肉眼回归不可靠 | 支持竖排或西文混排时需重定 |

---

## 10. R1 施工结果

### 10.1 怎么跑起来

**双击 `D:\WorkBuddy\projects\ai-teleprompter\start.bat`** 即可（会自动开控制台页面）。关掉那个黑窗口就停服务。

嫌 `start.bat` 黑窗口难看，也可以命令行：

```bash
cd D:\WorkBuddy\projects\ai-teleprompter
D:\WorkBuddy\venvs\default\Scripts\python.exe run.py
```

浏览器打开 **http://127.0.0.1:8756** → 控制台；点「打开提词窗」出第二个窗口（拖到相机镜头附近那块屏幕）。

- 端口上已有实例时不会报错，`run.py` 会直接打开那个实例（改用 HTTP 探测而非 `bind` 试探，因为 TIME_WAIT 会让 `bind` 误判成"被占用"）。
- 零构建：改 `web/*.js|css` 刷新即生效；改 `app/*.py` 需重启。
- 稿件落在 `data/scripts/*.md`，参数落在 `data/state.json`，删掉即恢复默认。
- **`start.bat` 是唯一的正式启动方式。** 我在会话里临时起的服务只是为了当场验证，会话结束就会被回收——所以如果你发现 `127.0.0.1:8756` 打不开了，双击 `start.bat` 即可，不是程序坏了。

### 10.2 已实现的清单

| 需求 | 落地情况 |
|---|---|
| 字号可随时调整 | 控制台滑块 24–160 px + `Ctrl+=/-`；提词窗按窗宽自动收敛（不超 `per_line` 宽度） |
| 文本可软件内编辑 | 左侧 textarea，800 ms 自动保存；`Ctrl+Z` 走浏览器原生 |
| 只在准备阶段可改 | 两态模型：`RUNNING/PAUSED` 时滑块、稿件选择、textarea 全部禁用 |
| 红线贴当前行底边 | 实测 gap = 8.2 px（`cue_gap_px`=8）；四个尺寸下都贴在 42% |
| 当前行上下位置可调 | 红线滑块 15–70%（几何不允许时自动钳位，见 §4.9） |
| 黑底白字 | `#000` / `#FFF`；已读 `#7A7A7A` |
| 读完的字变灰 | 双级：上方行整行灰（行级）+ 当前行已读字逐个灰（字级） |
| 开始后只有空格/Esc | 空格暂停继续、Esc 退出；其余键位与 `Ctrl/Cmd/Alt` 组合全部 `preventDefault` |
| 滚轮选当前行 | 40 px 阈值 + 50 ms 去抖；上方全灰、当前行及以下全白 |
| 窗口尺寸对齐适配 | `ResizeObserver` + rAF 合并 + resize 期间关过渡；红线 y、字号、平移量全部重算 |
| 红线保持原样 | 2 px 实心 `#FF2D2D`，暂停转 `#8A8A8A`，横贯整宽 |

### 10.3 自动化测试

| 文件 | 内容 | 结果 |
|---|---|---|
| `tests/test_script.py` | 切行 / 避头 / 标点阈值 / 拼音列 / `Motion` 收敛 | 20 项全过 |
| `tests/test_ws.py` | WebSocket 起停、空格暂停、滚轮双向、行内清零 | 12 项全过 |
| `tests/test_ui.py` | 渲染 / 参数联动 / 两态锁定 / 四尺寸自适应 / 滚轮染色 / 键位拦截 | 31 项全过 |
| `tests/shot.py` | 视觉回归截图（`D:\WorkBuddy\temp\shots\`） | — |

```bash
D:\WorkBuddy\venvs\default\Scripts\python.exe tests\test_script.py
NO_PROXY="*" D:\WorkBuddy\venvs\default\Scripts\python.exe tests\test_ws.py
NO_PROXY="*" D:\WorkBuddy\venvs\default\Scripts\python.exe tests\test_ui.py
```

### 10.4 需要你亲眼看一眼的四件事

自动化能测"红线离行底 8 px"，测不出"看着别扭"。请开提词窗跑一遍：

1. **红线是否始终贴在当前行底边**——尤其 F11 全屏、拖动窗口大小、拖到第二屏之后；
2. **滚轮拨动后，上方全灰、当前行及以下全白**——对得上吗；
3. **字变灰是否跟手**——有没有滞后或抢跑；
4. **录制中按其它键是否被拦**——字母、数字、`Ctrl+字母` 都不该有任何反应。

顺手拍一段 30 秒录屏回传即可。

### 10.5 一个想请你实测后再定的参数（我没动）

**红线高度 42% 是按你说的"保持现在的样子"留着的，但录口播时它可能偏低。**

笔记本摄像头在屏幕顶端，红线在 42% 意味着你念稿时眼睛要往下看一大截——录出来容易像"低头念稿"。行业里提词器的读数行通常放在 **1/3 甚至更低**，就是为了贴近镜头。

问题是对着这块屏念，红线越低 → 红线以上留给你"看已经念过的"越多、以下"能提前看的"越少：

| 红线位置 | 红线以上 | 以下完整前瞻（720p / 64px） |
|---|---|---|
| 42%（当前） | 3 行 | **3 行** |
| 30% | 2 行 | **4 行** |
| 25% | 1 行 | **4 行** |

建议：**先按 42% 录一条，再调到 28–30% 录一条，对比眼睛看的方向**。滑块就在控制台，改完立刻生效，不用重启。你定了我再把默认值改掉。

### 10.6 R2 开场清单（下一轮直接开工）

1. `audio.py`：`sounddevice` 采集 16 kHz 单声道，环形缓冲；设备选择与掉线重连；
2. `asr.py`：Qwen3-ASR-0.6B 流式推理（先跑通"准离线"：1.5 s 一块整段解码，不做流式状态机）；
3. 控制台加一块"识别回声"面板，显示最近 20 字 + 单块耗时 + RTF；
4. 先只跑 `cps` 模拟推进 vs ASR 文本的**对照日志**，不接线到渲染——目的是拿到真实延迟数字，把 §4.3 的 τ 定下来；
5. 模型下载（约 1.2 GB）会先问你要不要下、下到哪个盘。

**R2 的验收不看位置准不准**（那是对齐器的活），只看两件事：**识别得对**、**延迟能不能忍**。如果 0.6B 在你的 3060 Ti 上单块超过 300 ms，R3 之前要先解决推理速度，否则对齐器再好也白搭。

---

## 11. R2 施工记录（语音识别）

### 11.1 工程搬迁

用户要求：**模型和工程文件放在同一个 D 盘文件夹里，方便打包发给别人或上传开源平台。**
→ 新根目录 `D:\AITeleprompter\`，旧的 `D:\WorkBuddy\projects\ai-teleprompter\` 停用。

```
D:\AITeleprompter\
├── app\           config / script / session / motion / audio / asr / listener / store / server
├── web\           原生 JS 零构建
├── models\Qwen3-ASR-0.6B\   权重 1.75 GB
├── data\          稿件与偏好（用户隐私）
├── tools\download_model.py  断点续传下载器（纯标准库）
├── tests\         test_script / test_ws / test_ui / try_asr / shot + fixtures
├── run.py  start.bat  requirements.txt  README.md  .gitignore
```

三条纪律：

1. **所有路径从 `app/config.py` 的 `ROOT` 推导**（`ROOT = Path(__file__).parent.parent`），整个目录搬到哪都能跑。想换权重位置设 `TELEPROMPTER_MODEL` 环境变量。
2. **`start.bat` 按优先级找 Python**：`.venv\Scripts\python.exe` → `%TELEPROMPTER_PYTHON%` → 本机 D 盘虚拟环境 → PATH 里的 `python`。这样"原开发者机器"和"别人解压后"都能双击跑。
3. **模型不进 git，但进文件夹**。`model.safetensors` 单个 1.87 GB，GitHub 单文件上限 100 MB，推上去必失败；`.gitignore` 排除 `models/`、`data/`。压缩包直发不受影响。开源用户 clone 后跑 `python tools/download_model.py`。

> 一句话：**"文件夹里有模型"和"git 仓库里没有模型"不矛盾**，前者服务于压缩包直发，后者是平台硬限制。

### 11.2 权重下载实测

| 项 | 实测值 |
|---|---|
| 仓库 | `Qwen/Qwen3-ASR-0.6B`（ModelScope） |
| 文件数 / 体积 | 10 个 / **1.75 GB**（`model.safetensors` 1.87 GB） |
| 直链格式 | `https://www.modelscope.cn/models/{repo}/resolve/master/{path}` |
| 实测速度 | **~47 MB/s**，40 秒下完 |
| HuggingFace | **直连 8 秒超时不通**；`hf-mirror.com` 通 |
| 磁盘 | D 盘可用 105 GB，无压力 |

⚠️ **`huggingface.co` 在本机不通**，以后下模型一律先试 ModelScope。

### 11.3 识别链路

```
麦克风 → sounddevice 回调(16kHz mono) → 环形缓冲(deque, 30s)
      → 每 0.5s 取最近 4s → RMS 门限 → 单线程 executor 跑 ASR
      → 广播 {type:'asr', text, ms, rtf} / {type:'vu', level}
```

**实测（CPU / float32 / i5-13400F）**：

| 指标 | 数值 |
|---|---|
| 模型加载（含 transformers import） | 首次约 13.7 s，其中权重加载 **1.5–1.7 s** |
| 4.2 s 音频推理 | **1.28 s** |
| **RTF** | **0.30**（约 3.3× 实时） |
| 识别结果 | 「甚至出现交易几乎停滞的情况。」✓ |

结论：**CPU 就能跑，不装 CUDA 也能出结果**。但 0.5 s 一拍 + 1.3 s 推理意味着位置更新频率只有约 0.7 Hz，对"跟读"来说偏慢。
→ 想上 5–10 Hz 有两条路：装 CUDA 版 torch（预计提速 10×），或把窗口缩到 2 s（准确率会掉）。**R3 之前要先定这件事。**

### 11.4 依赖踩坑记录（这一段比代码值钱）

R2 花了大量时间在依赖矩阵上，四个坑各自都是几十分钟：

| # | 现象 | 根因 | 解法 |
|---|---|---|---|
| **P-1** | `ValueError: continue_final_message is set but the final message does not appear in the chat after applying the chat template` | 模型自带的 `chat_template.json` **只渲染 system + user + `<\|im_start\|>assistant\n`，根本不渲染 assistant 轮**；而 `processor.apply_transcription_request()` 依赖 `continue_final_message=True` 把 `language Chinese<asr_text>` 塞进 assistant 轮 | 别用那个便捷 API。**自己拼提示词**（格式短、可见、不随版本漂） |
| **P-2** | `ValueError: Qwen3ASREncoder expects padded_feature_length to be a multiple of n_window * 2 (100), but got 420` | 模型 `preprocessor_config.json` 里写的是**通用 `WhisperFeatureExtractor`**，而补 mel 轴的逻辑在没被启用的 `Qwen3ASRFeatureExtractor` 里 | **音频样本数补齐到 16000 的整数倍**（= 整秒）。补零等价于官方补 mel 轴 |
| **P-3** | `ValueError: Audio features and audio tokens do not match, tokens: 65, features: 65`（两个数明明相等） | transformers 5.23 的 `torch_compilable_check` 在该模型 forward 里误判 | 换回官方 `qwen-asr` 包（它自带一份 modeling，绕开这条路径） |
| **P-4** | `ImportError: huggingface-hub>=0.34.0,<1.0 is required ... found 2.4.0` / `TypeError: check_model_inputs() missing 1 required positional argument` | transformers 5.x 与 4.x 的 `huggingface-hub` 要求互斥；`qwen-asr 0.0.6` 是按 4.x 的内部 API 写的 | **锁 `transformers==4.57.6` + `huggingface-hub<1.0` + `qwen-asr==0.0.6`**。注意：`qwen3_asr` 架构在 4.57.6 里**不存在**（config 里的 `transformers_version: 4.57.6` 只是导出时版本），只有 5.x 有 —— 所以**走 qwen-asr 就必须待在 4.57.6**，走 transformers 原生就必须上 5.x |
| **P-5** | `pip install qwen-asr` 卡了 10 分钟无输出 | 顺带拉进 librosa / scipy / soundfile / soxr 一堆 | 耐心等；或 `--no-deps` 后自己按需装 |

**当前锁定组合（实测可跑）**：`torch 2.14.0(cpu)` + `transformers 4.57.6` + `huggingface-hub 0.36.2` + `qwen-asr 0.0.6`。

### 11.5 打包链路（把"方便打包"落成一条命令）

用户原话是「**方便打包发给别人或上传至开源平台**」。光有"一个文件夹"还不够 —— 手工框选目录压缩，一定会
把 `data\`（自己的稿子）、`.venv\`（几百 MB 的依赖）、`__pycache__\` 一起打进去，而且每次都得重新判断。
所以补了 `tools/package.py` 和 `setup.bat` 两件东西：

| 产物 | 命令 | 体积 | 给谁 |
|---|---|---|---|
| `code` | `python tools/package.py` | **168 KB** | 上传 GitHub / Gitee |
| `full` | `python tools/package.py --with-model` | **1.8 GB** | 压缩包直发朋友 |

- 默认排除 `data/`、`.venv/`、`__pycache__/`、`dist/`、`*.pyc/*.log`，与 `.gitignore` 保持同一套口径；
  `--with-model` 只额外放行 `models/`，**`data/` 仍然排除**（真要连稿子一起发得显式加 `--include-data`）。
- 归档内统一套一层顶层目录 `AITeleprompter\`，解压不会散一地。
- 模型权重几乎压不动（`safetensors` 是裸 float16），`full` 用 `compresslevel=1` 图快；纯代码用 6。
- `--list` 只列清单不出包，方便打包前检查。

`setup.bat` 解决"对方拿到之后"那一步：建本目录 `.venv\` → 装锁版依赖 → 问一句要不要下模型
（`models\` 里已有就跳过）。全程不碰系统环境。

**可移植性实测**（不是"应该能跑"，是真跑过）：

| 验证项 | 结果 |
|---|---|
| 把 `code` 包解压到 `D:\WorkBuddy\temp\pkgtest\AITeleprompter\` | ✓ |
| 新位置 `config.ROOT` 自动指到新路径 | ✓ `D:\WorkBuddy\temp\pkgtest\AITeleprompter` |
| 新位置跑 `tests/test_script.py` | ✓ 20 项全过 |
| 新位置另起服务（`TELEPROMPTER_PORT=8757`） | ✓ `/` `/prompter` `/api/state` 全 200 |
| zip CRC 校验 / 顶层目录 / 无 models·data·pycache | ✓ |

> 为此把 `PORT` 也改成读 `TELEPROMPTER_PORT` 环境变量（默认仍 8756）。
> 起因很具体：想验证解压副本能不能独立跑，而 8756 已被主实例占着 —— 这恰好也是用户的真实场景
> （"解压了新的，旧的还开着"）。

### 11.6 R2 剩下的活

- [ ] 把识别文本接到稿件定位（**这是 R3 的活**，不在 R2）
- [ ] 麦克风设备选择器（现在用系统默认，本机是 fifine USB 麦）
- [ ] 长静音时不重复识别同一段（现在靠“文本没变就不刷新”兜着）
- [ ] CUDA 版 torch（可选，决定位置更新频率）

---

## 12. R3 施工记录（对齐器 + GPU）

R3 的目标只有一个：**让红线跟着嘴走**。用户在这一轮开头拍板走 A（装 CUDA 版 torch）。

### 12.1 GPU 化：先纠正一个我自己量错的数

| 阶段 | 耗时（4.2 s 音频） | 说明 |
|---|---|---|
| CPU（R2） | 1280 ms | RTF 0.30 |
| GPU 首次调用 | 1208 ms | **含约 950 ms CUDA 预热** |
| GPU 稳态 | **251 ms** | **RTF 0.06，约 5.1×** |

⚠️ **第一次量的时候我以为「上了 GPU 和 CPU 一样快」（1297 ms vs 1280 ms）**，差点得出"显卡没用"的错误结论。两个测量错误叠在一起：

1. **测的是第一次调用** —— CUDA 首次推理要交"开机费"（kernel 加载 + cuBLAS/cuDNN 初始化），把这笔钱算进了稳态；
2. **没 `torch.cuda.synchronize()`** —— 连续调用时测到的是**入队时间**，不是算完时间。

补上预热和同步之后，真实数字是 251 ms。**教训：GPU 上的性能数字，不预热不同步就是废数。**

**对策（已落进代码）**：`AsrEngine._warmup()` 在模型加载完用 1 秒静音跑两遍，把预热成本挪到"开麦"这一步。实测预热只花 746 ms，换来的是用户开口第一句话不被吞掉。

安装过程的两个坑：

| # | 现象 | 根因 | 解法 |
|---|---|---|---|
| **G-1** | `pip install` 半小时只下到 77 MB（285 KB/s），而 `curl` 同一 URL 有 4.59 MB/s | pip 的下载通路在本机被代理拖慢 | **curl 直连下载到本地**，再 `pip install <whl>` |
| **G-2** | `ERROR: Invalid wheel filename (wrong number of parts): 'torch-cu126'` | 我把文件改名成 `torch-cu126.whl`，而 pip 靠**文件名**解析版本/ABI/平台 | 保持原名 `torch-2.14.0+cu126-cp313-cp313-win_amd64.whl` |

> 版本选择：torch 2.14.0 只提供 **cu126 / cu130** 的 Windows 轮子（cu128 最高到 2.11.0），取 cu126。

### 12.2 `app/align.py`：拼音 + 半全局 DTW

按 §4.2 实现，但有四处必须临场决断的地方：

| 问题 | 处理 |
|---|---|
| `Script.pinyin_window()` **会过滤标点**，返回的下标和 `chars` 不再对应，直接 `lo + end` 会偏出标点那么多个字 | 新增 **`Script.token_window()`**，把每个 token 对应的**字索引**一起带出来 |
| 位置正好落在逗号上时，**前面全灰了逗号还是白的**（"念完"按字索引算） | `new_pos` 跳过紧随其后的标点，让标点跟着一起灰 |
| 无 `cuda.synchronize` 时测的是入队时间 | 见 §12.1，基准一律加同步 |
| 真·同音字（是/事）的代价 | **实测为 0，不是文档里的 0.35** —— 两者拼音完全相同，在拼音层面本就不可区分。**这比预期更好，也正是走拼音的全部意义** |

**实测**：

| 指标 | 数值 |
|---|---|
| 20 字窗口（典型 4 秒） | 中位 **0.66 ms**，p95 0.81 ms |
| 30 字窗口（语速快） | 中位 **1.01 ms**，p95 1.15 ms |
| 规划承诺 | < 2 ms ✅ |

### 12.3 接线：双驱动 + 逐轮修复的真 bug

`Session` 有两个位置来源，**同一时刻只能有一个开车**：

```
模拟（cps 匀速）  ──┐
                    ├──▶ pos ──▶ Motion ──▶ 渲染
识别（对齐器）    ──┘
```

规则：**收到第一次高置信度对齐就切到识别驱动**，模拟让路；`stop()` 时释放。
滚轮是"人接管"，必须同时 `aligner.reset(pos)`，否则下一拍 ASR 立刻把位置拉回去（§4.5 早就写了，这里落实）。

⛔ **这一轮抓到的真 bug（不是测试问题）**：

> 用户开麦后模型要加载 13 秒。这 13 秒里如果按了空格，**模拟推进会按 4.2 字/秒把整篇稿子滚到结尾并自动置 IDLE**；等他开口，识别结果全被"非 RUNNING 状态"挡掉，表现为**完全跟不上**。

修法：`session.sim_enabled = not listener.on` —— 麦克风一开就关掉模拟。哪怕模型还没加载完、一句话都没识别出来，也宁可在原地等，不能按时间轴自己播。

### 12.4 节拍：原来每拍白睡一个 hop

```python
# 旧：先睡 hop 再干活 → 实际周期 = hop + 推理
await asyncio.sleep(hop); wav = ...; await infer()

# 新：按"开始到开始"算，只在末尾补足剩余
t_start = now; wav = ...; await infer(); sleep(max(0, hop - spent))
```

`hop_sec` 0.5 → **0.30**。但实测发现循环内的单次推理约 **575 ms**，而单独基准只有 227 ms —— 差的 350 ms 来自工作线程 + asyncio 事件循环抢 GIL（同一段代码在主线程跑就快）。**结论：循环内更新约 2 Hz，不是理论上限的 4.4 Hz。**

> 2 Hz 对"逐行跳变"是够的：一行 14 字按 4–5 字/秒要念 3 秒，位置每 0.5 秒刷新一次远超需要。
> 真要上 5 Hz，得把推理挪出线程池或换更小的窗口，收益不抵风险，R5 再评估。

### 12.5 测试（R3 当时 111 项，现 117 项）

| 文件 | 项数 | 覆盖 |
|---|---|---|
| `test_script.py` | 20 | 切行 / 注音 / 平滑 |
| `test_align.py` | **34** | 代价函数、半全局 DTW、正确 / 漏字 / 多字 / 同音 / 跳句、噪音、回退迟滞、会话驱动切换 |
| `test_ws.py` | 12 | WebSocket 状态机 |
| `test_ui.py` | 31 | 浏览器端渲染与按键 |
| `test_follow_e2e.py` | **5** | 样例音频 → ASR → 对齐 → 位置（不需麦克风） |
| `test_live.py` | **9** | **假麦克风灌音频进真实 Listener 循环**，验证「念稿真的会跟」 |

两个测试侧的坑：

- **`test_ws` 报 `InvalidProxyStatus: 502`** —— 这台机器全局设了 `HTTP_PROXY`，新版 `websockets` 会照着走，连 `127.0.0.1` 也去问代理。测试开头置 `NO_PROXY` 解决。**公司机器上跑本地服务的人都会踩这条。**
- **`test_live` 一开始 4 项失败** —— 表面像代码坏了，实际是测试没跑 60 Hz 心跳（`Motion` 不推进），以及上面那个"模拟跑飞"的真 bug 叠加。**测试不复现生产的心跳，就等于没测显示层。**

### 12.6 空间清理

| 项 | 体积 | 依据 |
|---|---|---|
| `nvidia/`（cublas/cudnn/nvrtc 的 pip 包） | **2.0 GB** | Windows 版 torch 把同样的 DLL 放在 `torch/lib` 里，两处同名同版本。**先改名 → 跑真卷积（cuDNN）+ 真实模型 → 都正常才删** |
| torch 安装包 `.whl` | 2.5 GB | 可重下 |
| pip 缓存 | 2.6 GB | 可重建 |

⚠️ **`models/Qwen3-ASR-0.6B` 没有删** —— 那是识别模型本体，删了就不能用了。用户说的"原来的模型"按**旧的 CPU 版 torch** 理解（已被 CUDA 版替换）。

### 12.7 R3 剩下的活

- [ ] CUDA 版 torch 装好后，README 里"CPU 也能跑"的措辞要再核一遍（已改）
- [ ] 长静音时避免重复识别同一段（现靠"文本没变就不刷新"兜着，R5 处理）
- [ ] 麦克风设备选择器（现在用系统默认 fifine）

---

## 13. 推进方式开关（用户追加需求）

用户原话：「**这个自动滚动速度与 AI 跟进语速有些冲突，我希望能做个开关切换两种模式，AI 自动跟进就在需要时跟进，不自己滚动**」。

### 13.1 冲突从哪来

R3 的设计是**隐式切换**：麦克风一开就关掉模拟，首次高置信对齐才切到 AI 驱动。问题有三层：

1. **用户没有选择权**——想用自动滚动就必须关麦，想用 AI 就必须开麦，而两者其实可以独立；
2. **开麦到第一拍识别之间是个空窗**（模型加载十几秒 + 首拍推理），这段时间文字完全不动，用户不知道是在等还是坏了；
3. **实现上用了三个布尔量**（`sim_enabled` / `asr_drive` / `listener.on`）表达同一件事，三处都可能不同步——R3 那个"模拟跑飞"的 bug 就是它们打架的产物。

### 13.2 收敛成一个字段

`ui["follow_mode"] ∈ {"auto", "ai"}`，**存在已落盘的 ui 里**，改它就是改配置，重启后还记得。
`Session.mode` 是个只读属性，直接读 `self.ui`——**不另存副本，不存在两处不同步**。

| 模式 | 位置怎么变 | 心跳 `tick()` | 识别结果 `feed_asr()` |
|---|---|---|---|
| `auto` | 按 `cps` 匀速 | 推进 | **直接丢弃** |
| `ai` | 只由对齐器决定 | **不动** | 采纳（置信度够才动） |

原 `sim_enabled` / `asr_drive` 全部删除；`asr_drive` 降级成纯显示的 `aligned`（"AI 已接上"）。

> 「不说话就不动」现在是**模式的直接后果**，不再需要额外标志去压制模拟推进——
> R3 那个 bug 从此在结构上不存在。

### 13.3 切换时的重锚（容易漏的一步）

`auto` 期间位置是 cps 推的，对齐器还停在它上次自己认为的地方。直接切到 `ai`，第一拍识别的窗口会以旧锚点为中心算，可能把画面往回拽一整段。

→ `Session.on_mode_changed()` 在切到 ai 时执行 `aligner.reset(int(self.pos))`。

### 13.4 界面

- 控制台最上方一个分段开关：`自动滚动 | AI 跟随`，选中项带蓝点；
- **AI 模式下「速度」滑块置灰**，右侧读数显示「不用」——留着亮蓝色拇指会让人以为它还在生效；
- 底下那行提示随模式与麦克风状态变化（AI + 未开麦 → "要先开麦克风"）；
- 开关**在录制中也允许点**：它只改行为、不改版式，不属于"防手抖"要锁的那类。字号/红线/稿件仍然录制中锁死。

### 13.5 测试

- `test_align.py` 新增 6 项：auto 忽略识别、auto 自走、ai 不自走、接上前后都不自走、stop 清 `aligned`、**auto→ai 重锚**（共 40 项）
- `test_ws.py` / `test_ui.py` **自行声明所需模式并在结束时还原** —— 测试不能依赖"用户上次选的是哪个"，否则一次手动切换就能让别人的回归挂掉
- 实机联调（`test_live.py`）复测：**14 拍 / 4.5 s ≈ 3.1 Hz，单次 249 ms**（此前的 2 Hz 是 GPU 被另一个实例争用所致）
- **新增统一入口 `tests/run_all.py`**：`python tests/run_all.py` 跑全部 **117 项**，`--fast` 只跑不要服务/模型的 60 项；缺前置（服务没起、模型没下、没装 playwright）就跳过并说明原因，不会假装通过

> ⚠️ **顺手堵掉一个假绿**：这些测试是脚本式的（自己维护 `OK/FAIL` 计数、靠 `check()` 断言，**没有 `assert`**）。
> 早先直接 `pytest tests/` 会按 `test_*` 名字把它们收成空壳函数，跑完报「14 passed」——
> 什么都没校验却显示全绿，比没测更危险。现由 `tests/conftest.py` 的 `collect_ignore` 显式挡掉，
> 唯一入口是 `run_all.py`。

---

## 14. 「AI 根本不跟随」：根因与修复

用户原话：「**AI 跟随模式开启提词器运行却没有这样的提示，我多次尝试均未跟随人声读稿语速跟进**」
—— 并给了一条决定性的线索：开麦克风时**有**"等待 AI 启动"的准备动作，AI 模式开始**没有**。

### 14.1 根因：开始录制时根本没开麦克风

```python
# 修复前
if t == "start":
    session.start()          # 只把 state 改成 RUNNING，就这些
```

`Session.start()` 只做四件事：位置归零、平滑归零、对齐器归零、`state = "RUNNING"`。
**它不碰 `listener`。** 于是：

| 用户动作 | 实际发生 |
|---|---|
| 切到 AI 跟随 | 只是 `ui["follow_mode"] = "ai"` |
| 点开始 | `state = RUNNING`，界面显示"跟读中" |
| 开口念稿 | **没有任何东西在听** —— `listener.on` 仍是 `False`，采集循环没启动 |
| 结果 | 稿子一动不动，而且连加载提示都没有（因为压根没开始加载）|

用户"开麦时有准备动作"恰恰印证了这一点：那条路径走的是 `/api/asr`，会真加载模型；
而 AI 模式的开始路径压根没走到那儿。

**这是设计缺陷，不是操作问题。** 选了 AI 跟随就意味着要用嘴驱动，那么"必须有耳朵"
应该是这个模式的隐含前提，让用户再去手动点一次「开启麦克风」是多余的——而且不点就静默失败。

### 14.2 修复：开始即接上耳朵

```python
if t == "start":
    session.start()
    if session.mode == "ai":
        await _ensure_ear()      # 没开麦就开，已经在听就跳过
```

`_ensure_ear()` 里用 `asyncio.create_task(listener.start())` 而**不是 await**：
加载模型要十几秒，await 会把这条 WS 消息挂住，前端按钮一直卡在按下状态。

`Listener.start()` 相应改成三段式，让"加载中"成为一个**可观测状态**：

| 阶段 | `loading` | `on` | 界面 |
|---|---|---|---|
| 点开始瞬间 | `True` | `False` | ⏳ 正在加载语音引擎（首次约 10–20 秒）… |
| 加载完成 | `False` | `True` | 🎤 在听 |
| 加载中点了停止 | `False` | `False` | 回到未开启 |

**加载期间被停止的竞态**：`_open()` 在 executor 线程里跑，用户中途点停止，
它跑完照样会把 `on` 置 True——人已经走了，麦克风还在听。用 `_gen` 代次号拦住：
`stop()` 让 `_gen += 1`，加载回来发现代次对不上就直接收掉麦克风返回。

**顺带改了 `_open()` 的顺序**：原来是「先加载模型、后开麦」，于是那十几秒里
用户说的话一个字节都收不到，引擎起来时人家已经念完一句了——又一个"我明明念了它没反应"。
现在**先开麦再加载**，声音留在环形缓冲里，加载完第一拍直接吃最近 4 秒。

### 14.3 状态条：让"没在动"这件事自己解释自己

`没跟随` 和 `程序坏了` 从外面看是一模一样的。所以 AI 模式下必须有一行字说明当前处境：

| 状态 | 文案 | 用户该做什么 |
|---|---|---|
| 未开麦 | ⚠️ 麦克风没开 —— 听不到你，稿子不会动 | 点开始（会自动开） |
| 加载中 | ⏳ 正在加载语音引擎…**不用重新点开始** | 等 |
| 在听但没声音 | 🎤 在听，但还没听到你说话 | 看 VU 条；不动就是麦没声/静音/选错设备 |
| 听到了但对不上 | 🎧 听到了，但对不上稿子：「最近识别到的字」 | **用滚轮把当前行拨到正在念的地方** |
| 正常 | ✅ 跟随中 · 置信度 0.xx · 最近识别 N 秒前 | — |

判据来自后端 `asr.last_at`（最后一次真正识别出文字的时间戳）——只看 `on=true`
是分不出"在听"和"在听但一个字没收到"的。前端每 500 ms 重算一次，内容没变就不动 DOM。

> `modeNote` 里原本也写着"要先开麦克风"，加载中时会和状态条自相矛盾
> （一边说"要先开"，一边已经在开了）。现在 `modeNote` 只讲规则，状态只由状态条一处表达。

### 14.4 删除稿件

- `store.delete_script()` + `DELETE /api/scripts/{sid}`
- 删掉的正好是当前稿件 → 自动切到剩下的第一篇；删光了 `seed()` 补回示例稿
- **录制中拒绝**（409）：正在念的内容瞬间失效，得先按 Esc
- 前端删除前把稿件名和字数摆进确认框——这个动作不可撤销，一句"确定吗"不足以让人看清删的是哪篇

⚠️ **路径穿越**：`sid` 直接来自 URL 并拼进文件名，`../../app/config` 这种能删到工程外面。
新增 `store.is_valid_sid()`，挡掉 `/ \ .. : * ? " < > |`、空串、超长、以点开头。
**读接口原本也有同样问题，这次一并挡掉。**

### 14.5 顺带修掉：窗口矮的时候模式开关点不到

诊断脚本量了四种窗口尺寸，发现 `segMode`（模式开关）与 `#previewBox` **重叠**：

| 窗口 | 预览框 | 模式开关 | 命中测试 |
|---|---|---|---|
| 1920×1080 | 66–309 | 321–367 | ✅ btnModeAuto |
| 1440×900 | 66–309 | **279–325** | ❌ previewBox |
| 1280×800 | 66–309 | **179–225** | ❌ previewBox |
| 1100×720 | 66–309 | **99–145** | ❌ previewBox |

原因是侧栏 `grid-template-rows: auto 1fr`：内容总高超出容器时行高被压塌，
两行叠在一起，`iframe` 的容器盖在按钮上面——**看起来"开关没反应"，其实是点在预览框上**。
（1280×800 是笔记本最常见尺寸，这一条会让用户以为 AI 模式坏了。）

改成 flex：`#previewBox { flex: 0 0 auto }` 保证它只按 16:9 定高、谁也压不动；
`.controls { flex: 1 0 auto }` 内容多就让侧栏整体滚动。四个尺寸复测全部命中正确元素。

### 14.6 测试（164 项）

| 文件 | 项数 | 本轮新增 |
|---|---|---|
| `test_server.py` | **33** | 新建：id 校验 17、删除 6、开始自动开麦 6（含"auto 不许开麦"回归） |
| `test_ui.py` | **45** | +14：三尺寸布局不重叠、AI 状态条、删除按钮锁定与真删 |
| 其余 | 86 | 未改 |

`test_server.py` 用**替换掉 `listener.start` 的假函数**来验证"会不会去开麦"，
毫秒级，不加载模型、不碰麦克风——真正的端到端仍由 `test_live.py` 负责。

⚠️ **测试不能依赖"上一次留下的当前稿件"**：`test_ui` 的行数断言一度因为
当前是短稿而失败（14 字/行和 10 字/行都切出 7 行）。现在开头固定写入
`_ui_fixture` 并在结束时删除。

---

## 15. 设置页与模型自动发现（v2.0）

### 15.1 需求

用户原话：「如何更改麦克风设备？在设置页选择载入的，干脆再开发几个可自指定的设置入口。」

拆成三件事：**换麦克风**、**换模型**、**给这些开个门**。

### 15.2 三层结构

| 层 | 放在哪 | 干什么 |
|---|---|---|
| 配置 | `config.DEFAULT_ASR` + `data/state.json` 的 `asr` 段 | `mic_index` / `model_dir` / `device` / `dtype` 四项，全部有默认值，不填也能跑 |
| 发现 | `app/model_finder.py` | **按内容**认模型目录：有 `config.json` + 权重文件就是，不认名字 |
| 接口 | `GET/PUT /api/settings`、`GET /api/devices`、`GET /api/models`、`POST /api/mic/test` | 页面只调这四个 |

发现层的候选顺序是刻意的：

```
models/Qwen3-ASR-0.6B/           ← 脚本下载的结果，优先
models/                          ← 用户把内容直接铺进来
models/*/                        ← 任意名字的一层子目录
models/*/*/                      ← 压缩包多套的那一层
```

实测把这四种都造了一遍（`tests/test_model_finder.py` 31 项），外加一次**真把 1.8 GB 文件夹改名**
的测试——`models/我随手改的名字-测试用/` 仍然能被找到。

### 15.3 三个设计决策

**① 录制中一律不准改（409）**
和「录制中不能删稿」是同一套安全观：正在用的东西不许中途抽走。
前端把整页灰掉并挂一条横幅说明原因，而不是让用户点了没反应。

**② 保存设置不加载模型**
`AsrEngine.reconfigure()` **只改参数**，真正加载仍等用户点「开始」。
否则一按保存就卡 10–20 秒导入 torch，界面看着像死了。

**③ 「变了才卸载」靠两个字段分开**
`model_pref`（用户选的，`None` = 自动找）与 `model_dir`（真正用上的绝对路径）分离。
早期把自动找到的路径写回偏好，导致下次保存时 `None != "D:\\...\\Qwen3-ASR-0.6B"`
被判成「改了模型」，白卸载重载一次。现在 `reconfigure()` 比较的是 `model_pref`，
同样的值存两次返回 `False`。

### 15.4 踩到的三个真 bug

**① `[hidden]` 被 `display: grid` 覆盖**
`.field { display: grid }` 是作者样式，优先级高于浏览器 UA 样式表里的 `[hidden] { display: none }`。
症状：「手动路径」那一行在选了「自动」之后**照样显示**（截图对比才发现）。
修法：显式写 `.field[hidden] { display: none; }`。

**② `mic_index` 里的 `0` 会被吞掉**
写成 `patch["mic_index"] or None` 的话，设备号 `0` 变成 `None`——而 MME 下 `#0`
（Microsoft Sound Mapper）是个**真实设备**。用户选了它，实际用的是「系统默认」，
选了个寂寞。修法：只把 `None` 和 `""` 当空，数字 0 原样保留，并为此单独加了断言。

**③ `download_model.py` 的 `--endpoint https://huggingface.co` 是假的**
脚本拼的是 `{endpoint}/api/v1/models/{repo}/repo/files`——这是 **ModelScope 独有的**
文件列表接口；下载链接写的是 `/resolve/master/{path}`，HF 用的是 `/resolve/main/`。
也就是说这个「海外用户改一下就行」的说明，改过去必 404。
修法：`_endpoint_guard()` 直接拦住 HF 并给出两条真正可行的路径（`hf download` 或网页手动下载），
不再假装支持。

### 15.5 实测数据

| 项 | 结果 |
|---|---|
| 本机输入设备 | **14 个**（含 fifine 麦克风 / 立体声混音 / HDMI） |
| 换设备开流 | `#0` `#1` `#2` 全部能以 **16 kHz** 打开，0.4 s 各采到 **6400** 样本 |
| 试音（安静环境） | 电平 **0.0001**，落在「几乎没声音」档——符合预期 |
| 设置落盘 | 关服务 → `state.json` 里是 `{"mic_index":1,"device":"cpu","dtype":"float32"}` → 重启后仍在 |
| 模型改名 | `Qwen3-ASR-0.6B` 改成任意名字，仍能定位（3 个候选位置内命中） |

### 15.6 已知不做

- **不并行加载多个模型**：换模型 = 卸载 + 重载，首次约 10–20 秒。
- **不处理热插拔**：拔掉正在用的麦克风会在下次开麦报错，不会自动切到别的。
- **采样率仍优先要 16 kHz**：要不到才退回设备默认率再重采样，不提供手动指定。

---

## 16. 启动器故障：点 start.bat 打不开（v2.0.1）

**症状**（2026-11-18 用户报）：双击桌面「AI提词器」图标，黑窗口打出
`系统找不到指定的路径` 和 `[x] 依赖没装好（缺 fastapi / uvicorn / numpy）`，随即退出。

### 16.1 两层故障，不是一件事

| 层 | 现象 | 根因 |
|---|---|---|
| ① 解析层 | `系统找不到指定的路径` / `'xxx' is not recognized as an internal or external command` | `start.bat` 存成了 **UTF-8 无 BOM + 满篇中文** |
| ② 环境层 | `[x] 依赖没装好（缺 fastapi / uvicorn / numpy）` | 本目录**没有 `.venv`**，退回 `PATH` 里的裸 Python |

两层必须分开修：只修①，用户会得到一句漂亮的中文提示说「缺依赖」；只修②，
黑窗口照样在解析阶段就崩，根本走不到依赖检查那一步。

### 16.2 ① 为什么 .bat 里绝对不能写中文

cmd.exe 读批处理是**按字节偏移 seek** 的，不是按行重读。`chcp 65001` 把代码页切成 UTF-8
之后，文件里中文的字节数按新代码页重算，偏移就对不上，cmd 从某个汉字的**半个字节**
处开始执行，把残片当命令。

实测（`cmd /c start.bat` 原样输出）：

```
[x] 依赖没装好（缺 fastapi / uvicorn / numpy）。
'�会把依赖装进本目录的' is not recognized as an internal or external command,
'或者手动：pip' is not recognized as an internal or external command,
```

第二行开头那个 `�` 就是被切在中间的汉字。

**规矩（已写进两个 bat 的头部注释）**：
- `start.bat` / `setup.bat` **一律纯 ASCII**。`chcp 65001` 保留，但那是给 Python 的输出用的。
- 所有面向用户的中文**交给 Python 打印**——`sys.stdout` 是流，没有字节偏移问题，
  在 `chcp 65001` 下 UTF-8 中文显示正常（已实测）。
- 想用中文 `title`？也不行，那一行同样参与偏移计算。窗口标题固定 `AI Teleprompter`。

**这就是「突然」的来源**：v2.0 加 `TELEPROMPTER_PYTHON` 支持时往 `start.bat` 里写了
大段中文注释和中文 `echo`，在那之前它没有中文，所以一直能跑。改动即故障，不是环境漂移。

### 16.3 ② 为什么退回裸 Python 必然失败

挑解释器的顺序是 `.venv` → `TELEPROMPTER_PYTHON` → `PATH` 里的 `python`。
前两者都不存在时（实测 `TELEPROMPTER_PYTHON` 未设置），落到
`...\Programs\Python\Python313\python.exe`（3.13.15，裸装），里面**只有 numpy**，
`fastapi` / `uvicorn` / `sounddevice` / `pypinyin` / `torch` / `transformers` 一个没有。

修法不是「教用户设环境变量」，而是**把 `.venv` 真正建出来**。这样桌面图标点下去
走的就是第 1 条路径，永远命中。

### 16.4 依赖自检从 bat 移到 run.py

原来 bat 里是 `"%PY%" -c "import fastapi, uvicorn, numpy"` + `if errorlevel 1`。三个问题：
1. 中文提示写不进 bat（见 16.2），只能出英文；
2. 只查 3 个包，`sounddevice` / `pypinyin` 缺了照样在 `import app.server` 处炸；
3. 报完就退出，不给修复路径。

改成 `run.py` 顶部的 `_missing_deps()`，用 `importlib.util.find_spec()` 而不是 `import`——
不执行模块、不触发 CUDA 初始化，几毫秒返回。

**刻意不查 torch / transformers / qwen-asr**：`app/asr.py` 里 torch 只在 `load()` 内部
才 import（第 53 行），起服务根本用不到。放进自检会造成「没装模型就连界面都不给开」，
比原故障更糟。这个分层是有意的，README 第 5 节也写了。

### 16.5 实测证据（修复后）

| 检查 | 结果 |
|---|---|
| `start.bat` 非 ASCII 字节 | **0 个**（`grep -P '[^\x00-\x7F]'` 无输出） |
| `cmd /c start.bat` | 无解析错误，中文提示由 Python 正常输出 |
| `.venv` 解释器 | Python 3.13.15，`pyvenv.cfg` 的 `home` 指向系统 Python，不依赖 WorkBuddy |
| `/` `/settings` `/prompter` `/api/state` | 全部 **HTTP 200** |
| `/api/settings` 设备列表 | 正确返回 14 个输入设备，默认标记落在 fifine 麦克风上 |

### 16.6 顺带修掉的两个 setup.bat 隐患

**① `&&` 绑错了对象**
```bat
rem 错的写法
if not defined PY where python >nul 2>nul && set "PY=python"
```
`&&` 绑的是**整个 if 语句**，不是后面的 `where`。当 `PY` 已有值（`py -3` 命中）时，
`if` 语句本身返回成功 → `&&` 成立 → 把 `py -3` **覆盖**成 `python`。改成显式括号：
```bat
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
```

**② 说一套装一套**
`requirements.txt` 只写 `torch>=2.4`，从 PyPI 默认源装到的是 **CPU 版**；
README 却说「装的是 CUDA 12.6 版」。用户按 README 期待 CUDA，装完发现是 CPU，
只会觉得「怎么这么慢」。改成 `setup.bat` 先单独问一句：

```
CUDA build : ~2.5 GB, needs an NVIDIA GPU, about 10x faster
CPU  build : ~200 MB, runs anywhere, slower but fine
Install the CUDA build? [y/N]
```

装完 torch 再跑 `requirements.txt`——此时 `torch>=2.4` 已满足，pip 会跳过，
不会把 CUDA 版覆盖成 CPU 版。

### 16.7 环境备注：pip 源

`%APPDATA%\pip\pip.ini` 配的是清华源。本次修复期间该源在当前网络下返回 **403**，
临时改用 USTC（`https://mirrors.ustc.edu.cn/pypi/simple`，实测 **99.7 MB/s**）。
`setup.bat` 已加降级：默认源失败自动用 USTC 重试一次。

torch 的 CUDA 版**只能**从 `https://download.pytorch.org/whl/cu126` 拿，任何 PyPI 镜像都没有。
这也是为什么它必须在 `requirements.txt` 之外单独装。

---

## 17. 发版流程（v2.0.1 起）

### 17.1 什么时候算一个版本

改完代码 → 本地 `python tests/run_all.py` 全过 → push 后 CI 绿 → 可以发版。

⚠️ 具体项数别照着旧数字写进文档：v2.0.1 时记的是 265 项，v2.2.4 是 `--fast` 194 /
完整 220（`test_ui.py` 因缺 playwright 被跳过），v2.3.0 是 `--fast` **249** /
完整 **320**（多了 `test_storage.py` 34 项），v2.4.0 是 `--fast` **271** /
完整 **342**（多了跨窗片段与稿尾两组用例）。
测试会增减，**以当次 `run_all.py` 打印的合计为准**，别把数字当契约。

补丁号（2.0.**x**）修 bug，次版本号（2.**x**.0）加功能。

### 17.2 四条命令

```bash
cd /d/AITeleprompter
git add -A && git commit -m "说明这次改了什么"
git push
git tag -a v2.0.2 -m "v2.0.2"
git push origin v2.0.2
```

tag 用**附注标签**（`-a`），不用轻量标签 —— 附注标签带作者、日期和说明，
`git describe` 也认得更准。

### 17.3 在网页建 Release

1. 打开 `https://github.com/BBsaba/ai-follow-teleprompter/releases/new`
2. **Choose a tag** 选刚推的那个（会显示 `Existing tag`）
   ⚠️ 不要点 "Create new tag"，tag 已经有了
3. 填标题和说明，点 **Publish release**

说明页至少要写清三件事：

- **这是什么**（一句话）
- **怎么装**（`setup.bat` → `start.bat`，两步）
- **zip 里不含模型**（1.8 GB 超限，靠 setup.bat 下）

第三点最容易漏，漏了下载者会以为解压就能用，然后卡在「依赖没装齐」。

### 17.4 为什么 Release 的 zip 不含模型

GitHub 对**单个文件**限制 100 MB。`models/Qwen3-ASR-0.6B/model.safetensors`
一个文件就是 1.75 GB，必然超限。

所以 `.gitignore` 排除 `models/`，靠 `setup.bat` 调 `tools/download_model.py`
首次下载。这个取舍是**故意的**，不是打包失误。

### 17.5 Release 附件放什么

**v2.2.4 起：放安装包。** `AI提词器-<版本>-安装程序.exe`（约 13 MB），改名为
`AITeleprompter-<版本>-Setup.exe` 再传（原因见 17.7）。

**v2.1 之前：什么都不用放**。GitHub 会为每个 tag 自动生成 `Source code (zip)` 和
`Source code (tar.gz)`，内容就是该 commit 的完整快照，够用。

想额外给「带模型的离线包」，用 `python tools/package.py --with-model`
打 1.8 GB 的 zip，但它贴着 GitHub Release **单文件 2 GB** 的红线，
上传又慢又容易断。**建议放网盘，不放 Release 附件。**

### 17.6 发版后验三件事

| 检查项 | 怎么看 |
|---|---|
| tag 指向对不对 | Releases 页面上那个 commit 短哈希和时间 |
| CI 绿不绿 | Actions 页面最近一次运行 |
| 源码包能下不 | 点一下 `Source code (zip)` 试试 |

### 17.7 ⛔ Release 附件名不支持非 ASCII（v2.2.4 实测）

本地构建产物叫 `AI提词器-2.2.4-安装程序.exe`。传成 Release 附件之后，名字变成
**`AI.-2.2.4-.exe`** —— 中文被 GitHub 当非法字符处理掉了。

试过的三条路，全部救不回来：

| 做法 | 结果 |
|---|---|
| 上传时 `name=` 用 UTF-8 百分号编码 | 落库后仍是 `AI.-2.2.4-.exe` |
| `PATCH /releases/assets/{id}` 改名 | 返回 **200**，但读回来名字没变（静默失败，最坑） |
| `json.dumps` 改 `ensure_ascii=False` 再 PATCH | 同样 200，同样没变 |

所以结论是：**Release 附件名只能用 ASCII**。发版时把本地文件重命名成
`AITeleprompter-<版本>-Setup.exe` 再传。本地 `dist/` 里保持中文名无所谓，
只有 Release 上那个名字会受影响。

⚠️ **改了 Release 上的名字，README 和 Release 正文里的下载文件名都要同步改** ——
否则用户照着 README 找 `AI提词器-2.2.4-安装程序.exe`，页面上只有
`AITeleprompter-2.2.4-Setup.exe`，会以为下错了。

> 上传用 `POST {upload_url}?name=...`，`Content-Type: application/octet-stream`，
> 整个文件读进内存一次 POST 即可（13 MB 不需要分片）。
> 验证方法：`curl -r 0-2047` 拉前 2 KB，开头两个字节应该是 `MZ`（PE 可执行）。

### 17.8 ⛔ `git push` 报 CRYPT_E_NO_REVOCATION_CHECK（v2.3.0 实测）

报错原文：

```
fatal: unable to access 'https://github.com/BBsaba/...': schannel:
next InitializeSecurityContext failed: CRYPT_E_NO_REVOCATION_CHECK (0x80092012)
```

根因：这台机器的出网走本机透明代理，**CRL / OCSP 的响应拉不回来**。schannel（Windows
的 TLS 实现）验完证书链之后还要查「这张证书有没有被吊销」，查不到就当失败。

| 做法 | 结果 |
|---|---|
| 只设 `http.schannelCheckRevoke=false` | ❌ 仍报同一个错 |
| 换 OpenSSL 后端 `http.sslBackend=openssl` | ❌ `unable to get local issuer certificate`（代理换了证书，自带 ca-bundle 认不出） |
| `GIT_SSL_NO_VERIFY=1` | ✅ 能过，但等于关掉全部证书校验，不该固化 |
| **`http.sslBackend=schannel` + `http.schannelCheckRevoke=false`** | ✅ **正解** |

**为什么单独设那一项没用**：git 只有在**明确知道后端是 schannel** 时才去读
`schannelCheckRevoke`；不声明后端，它走「自动探测」路径，压根不读这一项。
这条是查配置文档看不出来的，只能靠对照实验撞出来。

写进仓库 `.git/config`（不污染别的项目）：

```bash
git config http.sslBackend schannel
git config http.schannelCheckRevoke false
```

⚠️ 这只是**不查吊销列表**，证书链和域名照样验 —— 与 `sslVerify=false`（连「这证书是不是
github.com 的」都不问）有本质区别，别混为一谈。

3 秒复现的对照实验：

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://api.github.com                   # 000
curl -s -o /dev/null -w "%{http_code}\n" --ssl-no-revoke https://api.github.com   # 200
```

### 17.9 ⛔ 每次 push 都弹「Select a credential helper」（v2.3.0 实测）

现象：`git push` 弹出一个 `CredentialHelperSelector` 小窗，三个单选 `<no helper>` /
`manager` / `wincred`，底下还有「Always use this from now on」。选了 `manager`、勾了
「Always」，**下一次照样弹**。

根因不在仓库里。`credential.helper` 写在两个地方：

```
file:.../PortableGit/etc/gitconfig    credential.helper=helper-selector
file:C:/Users/admin/.gitconfig        credential.helper=!"...git-credential-manager.exe"
```

`credential.helper` 是**多值配置，git 会依次执行每一条**。系统级的 `helper-selector`
永远排最前，所以每次都先弹窗，用户选完 GCM 才被调用。

⚠️ **两个观测陷阱**（我两个都踩了）：

- `git config --get credential.helper` 只显示**最后一条**（GCM），看起来一切正常；
  必须 `--get-all` 才露出两条。
- 只查仓库级（`git config --get credential.helper` 在仓库目录里跑）也会误判 ——
  得 `git config --list --show-origin` 才看得出它们来自**不同文件**。

解法：用 git 官方的「空值重置」机制 —— 空字符串会把之前累积的列表**清空**：

```bash
git config --global --unset-all credential.helper
git config --global --add credential.helper ""      # 空值 = 清空
git config --global --add credential.helper "manager"
```

写出来是：

```ini
[credential]
	helper = 
	helper = manager
```

验证（不真推，只看调用了谁）：

```bash
GIT_TRACE=1 git push --dry-run origin main 2>&1 | grep -i credential
# 正确：只有 'git credential-manager get' / 'store'
# 错误：出现 'git-credential-helper-selector'
```

⛔ **不要去改 `PortableGit/etc/gitconfig`** —— 那是 WorkBuddy 自带 Git 的安装文件，
随应用升级会被覆盖，改了等于白改。

> 附带结论：`gh-release.py` 用的是 Windows 凭据库里的 token 走 REST API，
> 完全不受上面这套 git 配置影响。所以「能发 Release」和「能 push」是两条独立的链路，
> 一条通不代表另一条通。

---

## 18. 安装包：一个 13 MB 的 exe，替用户把命令行跑完（v2.1）

用户的原话是「**弄一个安装脚本程序，能够有一个小窗口让用户选择一些选项，然后这个小程序代替用户手动敲命令行的动作**」「**整体文件大小肯定是越小越好，好几个 G 有点夸张了**」。

这两句决定了整个架构：**安装包里不装货物，只装安装逻辑**。

### 18.1 为什么不是 PyInstaller，也不是「打个 1 GB 的大包」

| 方案 | 安装包体积 | 致命问题 |
|---|---|---|
| PyInstaller 冻结整个 torch | 1.5 GB+ | torch 的 CUDA DLL 有 30 多个、合计 3.6 GB，靠 hook 猜依赖**必漏**，装到别人机器上就是运行时 DLL 找不到 |
| Inno 里塞满 wheel（离线安装） | 1.0 GB | 用户要下 1 GB 才能开始装，而其中 2/3 是他可能用不上的 CUDA |
| **Inno + 官方 embeddable Python + 联网装依赖** | **13 MB** | 安装时要联网（这是刻意的取舍） |

最终结构：

```
AI提词器-2.1.0-安装程序.exe    13.0 MB   ← 用户下载这个
└─ 解开后
   python\      31.8 MB   官方 Python 3.13.15 embeddable + 预装好的 pip
   app\ web\ assets\       214 KB  项目代码
   run.py requirements.txt start.bat LICENSE README.md
```

压缩比 40.5%（31.8 MB + 0.2 MB → 13.0 MB，LZMA2/max）。

### 18.2 一条命令构建

```bash
python tools/build_installer.py              # 版本号默认 2.1.1
python tools/build_installer.py -v 2.2.0     # 指定版本
python tools/build_installer.py --skip-runtime   # 只改了代码时用，跳过重装 pip（省 40 秒）
python tools/build_installer.py --clean      # 清掉 build/ 重来
```

构建机要求：Windows x64 + [Inno Setup 7](https://jrsoftware.org/isdl.php)（免费）。ISCC 不在默认路径就用 `--iscc` 指过去。

产物落 `dist/`。`build/` 是中间产物（下载缓存 + payload），已进 `.gitignore`。

### 18.3 安装时到底发生了什么

```
欢迎 → 许可(AGPL) → 安装位置 → 选择运行方式(显卡/CPU) → 附加任务(桌面图标/下模型) → 开始安装
                                                                                    ↓
                                          解压 13 MB 文件（几秒，进度条这时就满了）
                                                                                    ↓
  ┌─ 进度条重置为 0，下面三步分别占 0–60 / 60–92 / 92–100 ─────────────────────────┐
  │                                                                                │
  │  pip_progress.py --mode torch   下 torch wheel 2.6 GB，再离线装                 │
  │  pip_progress.py --mode pip     -r requirements.txt（USTC 镜像）                │
  │  python -c "import numpy, sounddevice, pypinyin, fastapi, uvicorn, websockets"  │
  │  download_model.py --status …   模型 1.8 GB（勾了才跑）                          │
  │                                                                                │
  └────────────────────────────────────────────────────────────────────────────────┘
                                                                                    ↓
                                                                              完成页 → 启动
```

**进度条是连续的一条**：解压完先归零，之后每一步都在它那一段里往前走，状态栏同步显示「已下 / 总量 / 速度 / 剩余时间」。机制见 §18.5。

每一步的详细输出都写进 `{安装目录}\install.log`（由 pip 的 `--log` 参数写，不是 shell 重定向）。

装到 `%LOCALAPPDATA%\Programs\AITeleprompter`，**不需要管理员权限**；安装位置页可以改成任何目录（纯英文路径最稳）。

### 18.4 ⛔ 十一个坑，全是实测踩出来的

#### 坑 1：embed 的 `._pth` 会让 `import app` 直接失败

`python-3.13.15-embed-amd64.zip` 解压后有个 `python313._pth`。这个文件一旦存在，Python 就进入**隔离模式**：

- 只认 `._pth` 里列的路径
- **连「脚本所在目录自动进 `sys.path`」这条普通规则都取消**

于是 `python run.py` 报 `ModuleNotFoundError: No module named 'app'` —— 而同一份代码在开发目录里跑得好好的。

修法：`._pth` 里加一行 `..`（`python.exe` 在 `<安装目录>\python\`，所以 `..` 就是项目根）。

```
python313.zip
.
Lib\site-packages
..
import site
```

**但这条修法会被「复用 payload」偷走** —— 见坑 9。

#### 坑 2：`requirements.txt` 漏了 `websockets`，AI 跟随整个失效

`uvicorn` 裸装**不带** ws 协议实现。没有它，uvicorn 只打一行

```
WARNING: No supported WebSocket library detected.
```

然后页面照常打开、字照常显示，但**红线和文字一动不动** —— 症状极像「程序坏了」，其实是少一个包。

`app/server.py` 的 `/ws` 是唯一的推进通道（`web/prompter.js` 里只有 `new WebSocket(...)`，没有轮询兜底），所以这个包是**必需**的，只是开发机的 `.venv` 里恰好有，一直没暴露。

已修：`requirements.txt` 的 R1 段加 `websockets>=12`，自检命令也把它算进必需包。

#### 坑 3：`PrepareToInstall` 里检查文件，必然失败

Inno 的执行顺序是：

```
ssInstall（PrepareToInstall 在这里返回）
  → 复制文件（[Files]/[Dirs]/[Icons]）
  → ssPostInstall（这里才能动文件）
  → [Run]
```

第一版把 `if not FileExists(python.exe) then 报错` 写在 `PrepareToInstall` 里 —— 那一刻目录还是空的，`FileExists` 必然 False，于是：

> 用户在选项页全部顺利通过，一点「安装」立刻失败，而且目标目录**压根没建出来**，连 `install.log` 都没有。

⛔ **`PrepareToInstall` 里只能算路径，不要检查文件、不要写日志。** 这些全挪到 `ssPostInstall`。

#### 坑 4：Pascal 注释里不能出现 `{app}` 和 `[Run]`

Inno 的 `[Code]` 段是 Pascal：

- `{ ... }` 是注释。注释里写 `{app}`，那个 `}` 会把注释**提前截断**，剩下的文字变成代码 → `Syntax error`，而且行号指向注释中间，完全看不出是注释的问题
- `[Run]` 这种方括号**即使在注释里也会被当成段标签** → `Invalid section tag`

⛔ 注释里要提到安装目录就写「安装目录」，要提段名就写「Run 段」。

`installer/check_iss_comments.py` 专门扫这个，构建前跑一下。

#### 坑 5：`cmd /c` 的三层引号，失败了连日志都是空的

原本想用 `cmd /c ""python.exe" -m pip ... >> "install.log" 2>&1"` 把 pip 输出重定向进日志。这种串只要错一个字符就**静默失效**：退出码 1、日志是空文件、没有任何错误信息。

修法：**根本不碰 cmd**。pip 自带 `--log <file>`，日志交给 pip 自己写，一个引号都不用管。

```pascal
Exec(PythonExe, Args + ' --log "' + LogPath + '"', AppDir, SW_HIDE, ewWaitUntilTerminated, RC)
```

注意 `python -c "..."` 和 `download_model.py` 不认 pip 的参数，走另一个不带 `--log` 的函数。

#### 坑 6：`Format` 的数组参数换行顶格写，会被当成段标签

```pascal
Args := Format('--mode %s --status "%s"',
               [AMode, StatusFile]);        { ← 行首这个 [ 是段标签 }
```

ISCC 报 `Invalid section tag`，行号指向这一行的中间，看上去和数组毫无关系。同理，**注释里**写 `[Run]`、`[Setup]` 也会被当段标签（坑 4 的另一半）。

修法：把格式串先赋给一个变量，`Format` 那行不换行；或者把 `[` 留在行尾。

```pascal
Fmt  := '--mode %s --status "%s" ...';
Args := Format(Fmt, [AMode, StatusFile, ...]);
```

#### 坑 7：`Mode`、`Label`、`Stage`、`Text` 是保留字

写成 `function RunStage(const Mode, Label: String)` 直接 `Identifier expected`。

改名表：`Mode→AMode`、`Label→ALabel`、`Stage→AStage`、`Text→AText`。

#### 坑 8：`LoadStringFromFile` 要 `AnsiString`，`SplitString` 根本不存在

```pascal
var S: String;  F: AnsiString;
LoadStringFromFile(StatusFile, F);      { ✅ }
LoadStringFromFile(StatusFile, S);      { ❌ Type mismatch }
```

读一行文件最省事的写法是 `LoadStringsFromFile(StatusFile, Lines)` + `Lines[0]`（`TArrayOfString` 接受 Unicode）。切字段也别指望 `SplitString`——Inno 7 里它不接受 `TArrayOfString`，各版本签名还不统一，**手写十行 `Field()` 最省心**（见 `.iss` 里那段）。

#### 坑 9：装得上 ≠ 跑得起来 —— `--skip-runtime` 会把旧 payload 的毛病一起复用

这是**唯一一个到了用户手上才被发现**的坑，也是最贵的一个。

时间线：

1. 最早某次构建，`._pth` 还没加 `..`（坑 1 尚未修）
2. 坑 1 修好后，`prepare_runtime()` 里写的是对的
3. 但后面十几次调试性构建都加了 `--skip-runtime` —— **复用 `build/payload/python`，`prepare_runtime()` 根本没执行**
4. 于是那台「旧的、坏的」运行时被一遍遍打进安装包
5. 用户装完：安装日志漂漂亮亮，`site-packages` 5.2 GB，九个包全部 OK，日志停在 `[退出码 0]`
6. 点开程序：`ModuleNotFoundError: No module named 'app'`，窗口一闪就没了

**没有任何日志会说谎** —— 装包确实成功了。出问题的是「装完之后要执行的那份运行时」，而这一点在安装阶段完全不会暴露：pip 是从外面调进来的，它靠自己的 site 机制工作，不需要 `import app`。

两个防线现在都补上了（`tools/build_installer.py`）：

```python
# 1) 复用旧 payload 时也重写/核对 ._pth
if args.skip_runtime and (PAYLOAD / "python" / "python.exe").is_file():
    print("  跳过（--skip-runtime，复用现有 python/）")
    write_pth(PAYLOAD / "python")        # ← 幂等：已正确就只说一句

# 2) 编译前用 payload 自己跑一次 import，跑不通直接 SystemExit
def smoke_project_import() -> None:
    probe = PAYLOAD / "_import_probe.py"
    probe.write_text("OK = True\n", encoding="utf-8")
    ...  # 起子进程 import 它，探针跑完删掉，不进安装包
```

第 2 条是重点：**它是唯一能在构建阶段复现「用户点开程序」这件事的检查**。`import app` 依赖 fastapi 等第三方包、payload 里没有，所以用探针模块代替 —— 验的是「同目录进不进 `sys.path`」这一件具体的事。

教训一句话：**复用中间产物时，凡是「曾被修过」的地方都要重新校验，不能因为「上次跑对了」就跳过。**

#### 坑 10：`shellexec` 打开日志，「窗口闪一下就没了」

完成页那个「查看安装日志」原本这么写：

```pascal
Filename: "{app}\install.log"; Flags: postinstall shellexec skipifsilent unchecked
```

`shellexec` 走**系统文件关联** —— `.log` 在用户机器上关联到哪个程序，完全不可控。实测表现是点「完成」后一个窗口闪一下消失，用户什么都没看成，还以为安装失败了。

改成点名打开，并且**打开的不是 30 MB 的原始日志**：

```pascal
Filename: "{sys}\notepad.exe"; Parameters: """{app}\install-result.txt""";
    Description: "查看安装结果"; Flags: postinstall nowait skipifsilent unchecked
```

三点都要：

1. **`{sys}\notepad.exe` 写死**，不走关联，结果可预期
2. **`nowait`**：记事本是独立进程，安装器退出不该把它带走
3. **打开摘要而不是 `install.log`**：那份日志 34 MB，全是 pip 的下载链接，用户翻到眼花也看不出「到底成没成」

摘要 `install-result.txt` 由 `WriteResultFile` 在 `ssPostInstall` 末尾生成，几百字节：

```
AI 提词器  安装结果
==============================================
版本      2.1.2
安装目录  D:\text\AITeleprompter
时间      2026-11-19 18:20:57

运行环境  成功（fastapi / uvicorn / websockets / numpy / sounddevice / pypinyin 全部就位）
PyTorch   显卡加速版（CUDA 12.6）
模型      已下载完成（1.8 GB）

结论      安装成功，双击桌面图标就能用。

完整日志  D:\text\AITeleprompter\install.log
```

⚠️ 两份文件的编码规则**相反**，别搞混：

| 文件 | 写法 | 编码 | 理由 |
|---|---|---|---|
| `install.log` | `Log()` → `SaveStringToFile` | **只能 ASCII** | pip 的 `--log` 往里追加 UTF-8，混排会一半乱码 |
| `install-result.txt` | `WriteResultFile` → `SaveStringToFile` | GBK，可写中文 | 单独一份文件，不混 |

#### 坑 11：升级安装时，「选择安装位置」那一页会凭空消失

用户反馈：第一次装能看到选目录，装 2.1.2 时这页没了，直接跳过去。

原因是 Inno 6 起 `DisableDirPage` 的默认值改成了 **auto**：

> auto: Setup hides the Select Destination Location page if a previous version of the same application is already installed.

也就是说——**只要检测到同 AppId 的旧版本，就把选目录页藏掉**。第一次装（没有旧版本）正常，升级装就消失。开发者本地很难复现，因为测试机通常已经装过。

修法一行：

```ini
DisableDirPage=no
```

顺带把那一页的说明也改了（`[Messages]` 段），因为换目录的代价不是「挪文件」而是「重新下载」：

```ini
[Messages]
zhcn.SelectDirDesc=装到哪个文件夹由你决定。沿用上次的目录会复用已下载的依赖；换到新目录需要重新下载（显卡版约 2.6 GB，仅 CPU 约 240 MB）。
```

⚠️ `[Messages]` 的键名必须带语言前缀（本项目是 `zhcn.`），写错 Inno 会警告 `Message name not found`——所以**编译时不能忽略警告**，这次就是靠「零警告」确认键名对的。

### 18.5 真实进度：状态文件 + 每秒轮询

**不要**用 `CreateOutputProgressPage`。它是给**自定义向导流程**（在 `NextButtonClick` 里 Show/Hide）设计的，在「安装进行中」阶段强行切页风险大。

真正的问题是：**Inno 的 `Exec` 只拿得到退出码，读不到子进程的 stdout**；而 pip 的进度条一旦输出被重定向（不是真终端），就退化成「下完才写一行」。所以装 2.6 GB 的过程中界面一动不动 —— 用户实测的截图就是这样：进度条满格，状态栏停在一句话上十几分钟。

解决办法是让子进程把进度**写进一个文件**，Pascal 这边每秒读一次。

**协议**：`阶段|百分比|文字`，一行。

| 阶段 | 含义 |
|---|---|
| `LOOKUP` | 正在查版本 / 抓 wheel 链接 |
| `DOWNLOAD` | 正在下载，文字里带「已下 / 总量 / 速度 / 剩余」 |
| `INSTALL` | 正在解压安装 |
| `DONE` | 这一步成功，Pascal 继续往下走 |
| `FAIL` | 这一步失败，Pascal 中止 |

**两个 helper**（都在 `tools/`，都随安装包装进安装目录）：

| 脚本 | 管什么 | 关键参数 |
|---|---|---|
| `pip_progress.py` | 下 torch wheel、跑 pip 装其余依赖 | `--mode torch\|pip --status S --log L --tmp T --lo N --hi M` |
| `download_model.py` | 下 1.8 GB 模型权重 | `--status S --lo N --hi M` |

`--lo/--hi` 是这个阶段在总进度条上占的区间，所以进度条是**一条连续的线**：torch 0–60、其余依赖 60–92、模型 92–100。

**Pascal 侧**只有一个函数 `RunTracked(AParams, ALabel, var RC)`，`RunStage` 是给它拼参数的一层薄壳。轮询循环里四个要点：

```pascal
repeat
  WaitTick;                                    { 见下：不能用 Sleep }
  if LoadStringsFromFile(StatusFile, Lines) then
  begin
    AStage := Field(Lines[0], '|', 0);
    Pct    := StrToIntDef(Field(Lines[0], '|', 1), 0);
    if AStage = 'DONE' then begin RC := 0; Result := True; Exit; end;
    if AStage = 'FAIL' then begin RC := 1; Exit; end;
    if Pct > WizardForm.ProgressGauge.Position then   { 只许往前走 }
      WizardForm.ProgressGauge.Position := Pct;
    SetStatus(Field(Lines[0], '|', 2));
  end;
  ...
until False;
```

1. **`WaitTick` 用 `ping -n 2 127.0.0.1`，不能用 `Sleep`。** `Sleep` 期间不处理消息队列，窗口会变「未响应」；`Exec` 返回时会处理一遍消息，界面就活了。
2. **进度只许前进。** 多个阶段共用一个进度条，后退比不动更让人怀疑。
3. **卡死判定分两级。** 状态文件 30 秒没出现 → 助手根本没起来，立刻报错；有文件但进度 20 分钟没变 → 认为卡死。总上限 3 小时。
4. **开工前 `DeleteFile(StatusFile)`。** 否则上一阶段的 `DONE` 还在，新阶段一进去就被判成功。

**实测证据**（安装布局下真跑，中途 kill）：

```
DOWNLOAD|93|正在下载语音识别模型（1.8 GB）  200.7 MB / 1.8 GB  26.5 MB/s  剩 1:00
```

93% 是 200.7/1843 映射到 92–100 区间后的值，不是写死的。

**一个副作用值得知道**：`pip_progress.py` 抓 wheel 直链（先用 urllib 拉索引页正则挑 URL）比 `pip install torch==X --index-url ...` 快得多 —— 后者实测在「逐条比对几千个 wheel 的平台标签」上花了 **5 分钟**（17:02:38→17:07:50 全在 `Skipping link: none of the wheels tags ... compatible`），直链只要 1.3 秒。

### 18.6 卸载行为

- 程序文件和 `python\Lib\site-packages` 里的依赖：直接删
- `_tmp\`（下载缓存、进度文件）：直接删
- `install.log`、`install-result.txt`：显式 `DeleteFile` —— 它俩不在 `[Files]` 里，
  不删就会在卸载后孤零零留在目录里
- `data\`（稿子、界面设置）：**弹框问**，默认不删
- `models\`（1.8 GB）：**弹框问**，默认不删

### 18.7 安装包不该进 git

`dist/` 和 `build/` 都在 `.gitignore` 里。13 MB 的 exe 上传到 GitHub Release，不进仓库。

### 18.8 想验证「进度是真的」，得装到空目录

`site-packages` 和 `models\` 都在安装目录里、不在 `[Files]` 里。**重装到同一个目录**时 Inno 只覆盖那 13 MB 程序文件，依赖和模型原封不动 —— pip 一看「已满足」就跳过，模型脚本一看「文件都在」就秒写 `DONE`。

于是界面表现是：进度条唰一下到头，什么都没下载。**这不是进度条坏了，是确实没东西可下。**

验证进度显示的正确姿势：选一个**空目录**（`D:\text\AITeleprompter-test` 之类），或者干脆先选「仅用 CPU」—— 只下 240 MB，一分钟内就能看到速度、剩余时间在跳，验证完把测试目录删掉即可。真要用显卡版再装回原目录。

### 18.9 装完怎么确认「真的能开」（30 秒，不看日志）

安装日志只能证明包下载成功，证明不了程序能起来（坑 9 就是这么漏过去的）。真正要看的是：

```bat
cd <安装目录>
python\python.exe -c "import sys; print(sys.path)"
```

这条命令不依赖任何第三方包。**输出里必须有安装目录本身**（`D:\text\AITeleprompter`），没有就是 `._pth` 少了 `..`。

```bat
python\python.exe run.py
```

能起来就会打印地址并打开浏览器。

如果双击图标**窗口闪一下就没了**，说明 Python 的报错被启动脚本吞了 —— 用开始菜单里的**「排查启动（带命令行窗口）」**，同样的启动流程，但报错留在窗口里。

### 18.10 双击 `run.py` 也能用：启动时自愈

`.py` 在 Windows 上关联给 **py.exe 启动器**，它按 PATH / 注册表挑系统里装的 Python。用户刚用安装包装好，双击 `run.py` 得到的是：

```
[提词器] 依赖没装齐，服务起不来。缺这几样： sounddevice、pypinyin、fastapi…
[提词器] 现在用的是： C:\Users\…\Programs\Python\Python313\python.exe
```

然后一屏「去建 venv」的教程。**这在逻辑上是错的** —— 依赖明明装好了，只是装在 `<安装目录>\python\` 里，而启动器挑的是另一个解释器。

修法是在 `run.py` 开头加一段自愈（`_reexec_with_bundled_python`）：

```python
own = Path(__file__).resolve().parent / "python" / "python.exe"
if own.is_file() and Path(sys.executable).resolve().parent != own.parent:
    raise SystemExit(subprocess.call([str(own), __file__], env={..., "AITP_REEXEC": "1"}))
```

四个细节，每个都对应一个真会踩的坑：

| 细节 | 不这么做会怎样 |
|---|---|
| 比**目录**不比文件名 | 桌面快捷方式用的是 `pythonw.exe`（无控制台），比文件名会把它误判成「需要重启」 |
| `AITP_REEXEC` 环境标记 | 自带运行时万一也认为「不对」就无限重启 |
| `subprocess.call` 而非 `os.exec*` | Windows 上 `exec*` 和 POSIX 差得远；用 call 还能把退出码原样带出去 |
| 找不到自带运行时（源码目录）直接 `return` | 开发时在仓库里跑 `run.py` 会被跳去 `build/payload` 的运行时 |

效果（实测，用系统 Python 模拟双击）：

```
[提词器] 改用自带运行时：D:\text\AITeleprompter\python\python.exe
[提词器] 控制台   http://127.0.0.1:8756/
[提词器] 提词窗   http://127.0.0.1:8756/prompter
```

顺带把「依赖没装齐」的提示分了岔：**安装版不再教用户建 venv**（他没有源码），改成「重新运行安装程序」；只有源码目录才显示 venv 那三条。

### 18.11 卸载到底删什么（怕删到源码时的核查方法）

卸载程序看着吓人，其实它的删除范围完全由 `unins000.dat` 里的记录决定。**直接读它**比猜可靠：

```python
dat = Path(r"D:\text\AITeleprompter\unins000.dat").read_bytes()
text = dat.decode("utf-16-le", errors="ignore")          # 路径以 UTF-16LE 存
paths = set(re.findall(r"[A-Za-z]:\\[^\x00\"<>|\r\n]{3,200}", text))
```

实测结果（v2.1.0 装完后）：

| 位置 | 条数 | 说明 |
|---|---|---|
| `D:\text\AITeleprompter\…` | 1144 | 程序文件 + `python\` 运行时 |
| `C:\ProgramData\Microsoft\…Start Menu\…` | 7 | 开始菜单快捷方式 |
| `C:\Users\Public\Desktop\…` | 2 | 公共桌面快捷方式 |
| **源码仓库 `D:\AITeleprompter`** | **0** | 一条都没有 |

所以「卸载会不会删掉我的源码」的答案取决于**安装目录和源码目录是不是同一个**。这个项目的约定是：源码在 `D:\AITeleprompter`（git 仓库，带 `build/`、`installer/`、`docs/`），装出来的程序在别处（`D:\text\AITeleprompter`），两者物理隔离，卸载互不影响。

⚠️ 卸载时两个弹框的默认值都是**否**，别手快：

- `data\` —— 你写的稿子和界面设置，删了不可恢复
- `models\` —— 1.8 GB 权重，删了下次要重下

保留 `models\` 的话，重装到同一目录可以直接复用（`download_model.py` 会跳过已完整的文件）。

### 18.12 中途取消：为什么按钮会变灰，以及怎么让它真的停下来

用户在下载 2.6 GB 的中途按「取消」，界面卡住不动，按钮变灰。

**Inno 的取消机制有个前提**：它把取消按钮置灰、记下「用户要取消」，然后**等当前正在执行的 Pascal 代码把控制权交回来**才会真正中止。而我们的 `CurStepChanged(ssPostInstall)` 里是一个跑几十分钟的轮询循环 —— 从头到尾不让出控制权，于是：

- 用户看到按钮灰了 → 以为在取消
- 实际上下载还在继续，界面停在「正在安装」

**第二个坑**：Inno 拿不到 `Exec` 起来的子进程 PID，安装器手上没有句柄可以杀。而按镜像名 `taskkill /IM python.exe` 会误伤用户自己开的 Python。

所以取消要分两半：**Pascal 侧认信号，Python 侧收手**。

**Pascal 侧**：两处配合。

```pascal
{ 安装阶段开头先明确打开一次。Inno 在某些阶段会把它留在灰的状态，
  用户以为不让取消 —— 他反馈的就是这个。 }
WizardForm.CancelButton.Enabled := True;

{ 轮询循环里：按钮被置灰 = 用户确认了取消 }
if (Ticks > 3) and (not WizardForm.CancelButton.Enabled) then
begin
  UserCancelled := True;
  SaveStringToFile(CancelFile, 'cancel', False);   { 给 helper 的暗号 }
  WaitTick; WaitTick; WaitTick;                    { 给它三秒收尾 }
  Exit;
end;
```

两个细节：

- **前 3 秒不查**：刚进循环时按钮可能还没画出来，`Enabled` 是 False，会误判成「用户取消了」
- **只在开头置 True**：用户点取消后 Inno 会置灰，那是信号，循环里再置 True 就把信号抹了

取消时要**跳过后续的错误弹框**，否则用户主动取消还会看到「运行环境没装好」：

```pascal
if not DepsReady then
begin
  if UserCancelled then Exit;     { Inno 会回滚，别再添乱 }
  MsgBox('运行环境没装好：' + FailReason, ...);
end;
```

**Python 侧**：两个 helper 都加了 `--cancel <文件>`，每 0.3 秒看一眼这个文件在不在。

```python
def cancelled() -> bool:
    return CANCEL_FILE is not None and CANCEL_FILE.exists()
```

- `download_model.py` 在下载循环里检查，命中就抛 `_Cancelled` 收工
- `pip_progress.py` 在下载循环里检查，在 pip 子进程循环里检查（命中就 `proc.kill()`——用 kill 不用 terminate，Windows 上 terminate 只是 `WM_CLOSE`，控制台程序经常收不到）

实测（下载模型 5 秒后创建取消文件）：

```
FAIL|0|正在下载语音识别模型已取消
已下 64K（只下了两个小文件就停了）
```

**取消之后会留下什么**（用户该知道，不然会以为没卸干净）：

| 内容 | 取消后 | 说明 |
|---|---|---|
| 那 13 MB 程序文件 | Inno 回滚删除 | 正常 |
| `python\Lib\site-packages`（几 GB） | **保留** | pip 装的，不在 `[Files]` 里，Inno 不知道它们 |
| `models\`（1.8 GB） | **保留** | 同上 |
| `_tmp\cancel.flag`、半截 wheel | 残留 | 下次安装会被覆盖/忽略 |

这是好事：下次重装到同一目录，依赖和模型直接复用，不用重下几个 GB。

### 18.13 把长任务搬出 Inno 的窗口（v2.2.0，推翻 18.12 的做法）

18.12 那套「Pascal 认按钮信号」在真机上**不成立**。用户装上 2.1.3 之后反馈：

> 取消按钮的颜色对了，但是还是点不动，右上角的最小化以及关闭按钮也是没有交互反应

不是颜色没置对，是**整个窗口死了**。最小化、✕、取消，三个全都没反应 —— 这个现象本身就是决定性证据：只有 **输入消息** 进不来才会这样。

**真正的原因**：Inno 在执行 Pascal Script 时不派发输入消息。Pascal 代码跑在 Inno 主线程里，`while` 循环不返回，Windows 的鼠标/标题栏消息就堆在队列里没人取。

那为什么用户看到「进度条在动、文字在变」？因为 `SetStatus` 里调了 `Label.Update` —— 那是**同步重绘**（`UpdateWindow`），只处理 `WM_PAINT`。于是界面「看起来活着」，但一个点击都收不到。这也解释了为什么 18.12 的自测「5 秒后取消成功」是假的：那次是我手写了个 `cancel.flag` 文件，只验证了 Python 侧，没验证按钮。

⚠️ **判断窗口是不是真的活着**，别看它有没有在刷新，看它响不响应 `WM_NULL`（`IsHungAppWindow` / `SendMessageTimeout` + `SMTO_ABORTIFHUNG`）。`Update` 出来的刷新会骗人。

**新分工**（`DisableDirPage` 那些页面设置不变）：

| 层 | 谁 | 干什么 |
|---|---|---|
| 页面 + 复制文件 | Inno（`installer\AI提词器.iss`） | 收目录/组件/任务，铺 13 MB 文件，然后**把向导藏起来** |
| 进度窗口 | `tools\prep-ui.ps1`（PowerShell + WinForms） | 独立进程、独立消息循环 —— 最小化/关闭/暂停/取消全是真的能用 |
| 干活 | `pip_progress.py` / `download_model.py` | 下 wheel、跑 pip、下模型，把 `STAGE\|pct\|文字` 写进 `_tmp\progress.txt` |
| 体检 | `tools\check_env.py --json` | 报 torch 版本 / CUDA / 缺哪些包 / 模型在不在 |

Inno 只做一件事：`Exec(powershell -File prep-ui.ps1 ...)` 阻塞等着，然后读 `_tmp\prep-result.txt` 的三行 ASCII（`state=` / `stage=` / `code=`）。中文一句话都不回传 —— Inno 的 `LoadStringsFromFile` 拿 `AnsiString`，中文必乱码。

**退出码契约**（三处必须一致：iss、ps1、两个 py）：`0 成功 / 3 取消 / 4 失败或暂停`。

两个只有真跑才会发现的坑：

1. **`-WindowStyle Hidden` 会把 WinForms 窗口一起藏掉**。Windows 规定进程的第一次 `ShowWindow` 忽略参数、改用启动信息里的值，而 Inno 用 `SW_HIDE` 启动我们 —— 表现是「脚本跑了，窗口不出现」。修法：在 `Add_Shown` 里显式 `ShowWindow(hwnd, SW_SHOW)` + `SetForegroundWindow`。
2. **`.ps1` 必须是 UTF-8 带 BOM**。PowerShell 5.1 读不带 BOM 的 UTF-8 会按 ANSI 解，中文注释里的一个字符就能把后面的引号吃掉，报的错还指在几十行之外（`MissingEndCurlyBrace`）。构建脚本里写死 `encoding="utf-8-sig"`。

**增量安装**（避免「取消一次就白下 2.6 GB」）：

- `check_env.py` 先体检，已满足的步骤**整段跳过**：torch 版本对了就不再下；六个必需包 + 四个 ASR 包齐了就不再跑 pip；模型目录在就不再下
- torch wheel 下到 `_tmp\torch-download.whl`，**取消/暂停/断网都不删**，靠 HTTP `Range` 续传；旁边留一份 `.url` 记当初的地址，地址变了才丢掉重下（否则会拼出一个大小看着对、解压报 CRC 错的包）
- pip 不再用 `--no-cache-dir`，改成 `--cache-dir _tmp\pipcache`（在 D 盘，不占 C），重跑时已装的包 pip 自己会跳过
- `torch-download.whl` 只在**装成功**之后才删

**暂停**用文件当暗号（`_tmp\pause.flag`）：helper 在下载循环里看到就写 `PAUSED|pct|文字` 然后以 4 退出；窗口把按钮变成「继续」，点了就删掉暗号重跑同一阶段，从 `.part` 续上。解压安装阶段不能暂停（pip 正在写 site-packages，掐了会留半个包），窗口会把按钮置灰并说明原因。

**点 ✕ 等于取消**，会弹确认框 —— 不能让它「悄悄关掉、下载还在后台跑」。

实测（假下载脚本，不联网，用 `BM_CLICK` 模拟真人点击按钮）：

| 操作 | 结果 |
|---|---|
| 点「暂停」 | `PAUSED|86|model 已暂停在 0.1 MB`，阶段退出码 4 |
| 点「继续」 | 暗号被清掉，同一阶段重新开始 |
| 点「取消」 | `FAIL|0|model 已取消`，退出码 3，窗口自行关闭 |
| 全流程（已装齐的机器） | 4 秒走完，`state=ok`，一个字节都没下 |

**还有一个工具链的坑**：ISCC 7 把版本号开关从 `/D` 改成了 `-d`。用老写法会报
`You may not specify more than one script filename` —— 它把 `/DMyAppVersion=2.2.0` 当成了第二个脚本文件名。`build_installer.py` 里两种写法都试一遍。

**升级到 v2.2.0 之后，取消不再回滚那 13 MB 程序文件**（活搬到了 ssPostInstall，取消时文件已经装好，Inno 的回滚机制够不着）。取消后完成页会明确写「安装已取消、程序暂时用不了、重跑只补没完成的部分」，不写「安装完成」——这一点靠 `CurPageChanged(wpFinished)` 改文案，写在 `CurStepChanged` 里会被 Inno 覆盖掉。

### 18.14 点快捷方式毫无反应：pythonw 把 stdout 变成了 None（v2.2.1）

v2.2.0 装得很顺利（增量检测也对了），但用户装完点完成页的「立即启动」、再点桌面快捷方式，**两次都毫无反应**，连黑框都没有：

> 完成时我选择了立即启动提词器，但是却毫无反应，黑色cmd窗口也没有出现

「黑框没有出现」这一句其实是**设计如此** —— 快捷方式指向 `pythonw.exe`（GUI 子系统，不分配控制台）。所以真正的问题是：连浏览器都没打开、任务管理器里也没有进程。

**先把三个「像」的嫌疑排掉**（都实测过）：

| 嫌疑 | 怎么排的 | 结果 |
|---|---|---|
| 快捷方式指错了 | 读 `.lnk` 二进制里的路径串 | 目标 `python\pythonw.exe`、参数 `"…\run.py"`、工作目录都对 |
| 依赖没装齐 | 用自带 `python.exe` 跑体检脚本 | 六个包全 OK，`import app.server` OK |
| `_pth` 少了 `..`（§18.4 踩过） | 读 `python\python313._pth` | 四行齐全，含 `..` |

**决定性的一步是「能否复现」**。同一个 `run.py`：

```bat
rem 能跑 —— stdout 被重定向到一个真实文件
python\pythonw.exe run.py > out.txt 2>&1     → 端口 8756 起来，HTTP 200

rem 不能跑 —— 和用户点快捷方式完全一样的路径
cmd /c start "" "C:\Users\Public\Desktop\AI 提词器.lnk"   → 什么也没有
```

差别只有一个：**有没有一个真实的 stdout**。

**根因**（拿到原始调用栈后才看见）：

```
uvicorn\logging.py:42   self.use_colors = sys.stdout.isatty()
AttributeError: 'NoneType' object has no attribute 'isatty'
  → logging.config.dictConfig 失败
ValueError: Unable to configure formatter 'default'
  → uvicorn.run() 在 Config() 里就抛，端口还一个字节都没监听
```

`pythonw.exe` 没有控制台，CPython 于是把 `sys.stdout` / `sys.stderr` 都设成 `None`。uvicorn 0.54 的 `DefaultFormatter.__init__` 无条件调用 `sys.stdout.isatty()` —— 在 `None` 上取属性直接炸。而且**这时候 stderr 也是 `None`，traceback 连一个字都没地方写**，进程静悄悄退出。用户看到的就是「点了，什么也没有」。

⛔ 由此得到一条通用结论：**`pythonw` 下所有 `print` 都是空操作**（`print` 遇到 `sys.stdout is None` 会直接返回，不报错）。任何面向 GUI 子系统的 Python 程序，「静默消失」都必须先怀疑 `stdout is None`，而不是先怀疑快捷方式或打包。

**三层修法**（`run.py`）：

1. **`_ensure_streams()`** —— `main()` 第一件事就给两个流接上真实文件：
   - 首选 `data\launch.log`，占位不可写就退 `%TEMP%`，再不行 `os.devnull`
   - 关键不在「记录」，而在于**`sys.stdout` 必须是个有 `isatty()` 的对象**，哪怕它把字都扔掉
   - 用**追加**不用覆盖：已经有一个实例在跑时再点一次也会走到这里，覆盖会把正在运行那份的启动记录抹掉
2. **`_notify()`** —— 无控制台时改弹 `MessageBoxW`。以前「缺依赖」那条路径也是 `print` + `input()`，在 pythonw 下等于什么都不发生；现在会真的弹出来告诉你缺哪几个包。同理 `webbrowser.open` 返回 False 时弹窗给出 URL（服务已经起来了，别让人干等）。
3. **`__main__` 最后一道网** —— 万一在 `_ensure_streams` 之前就崩了（import 期），直接写文件 + 弹窗，不信赖 `sys.stderr`。

顺手改掉一句会误导人的话：无控制台时不再打印「关掉本窗口即停止服务」——**根本没有那个窗口**。

验证（`v2.2.1`，装完立刻点桌面快捷方式）：

| 检查 | 结果 |
|---|---|
| `GET /` | 200，3419 B |
| `GET /prompter` | 200 |
| `GET /api/state` | 200，返回完整 ui 配置 |
| `data\launch.log` | 有「启动 / 程序 / 目录 / 控制台 无（pythonw）」四行 |
| 再点一次快捷方式 | 识别到已有实例，`webbrowser.open` 后以 0 退出，不起第二份 |
| 控制台版 `python.exe run.py` | 照常打印，`_HEADLESS=False`，不弹窗 |

⚠️ 调试这类问题有个容易踩的坑：本机 `curl` 会走系统代理，服务停了以后代理返回的是 **502 + `upstream connect failed`**，看起来像「服务活了但接口坏了」。判断端口有没有人监听要用 `curl --noproxy '*'`。

### 18.15 安装时程序还开着：从几十个弹窗到一句话（v2.2.4）

用户实测（20:40）：

> 为了任务继续我只能一个个跳过了……这要跳过的也太多了

截图里的框是：

```
D:\text\AITeleprompter\python\libcrypto-3.dll
尝试替换已存在的文件时出错：DeleteFile 失败；错误代码 5。拒绝访问。
  → 重试(T)   → 跳过此文件(S)（不推荐）   → 取消安装
```

**根因**：`pythonw.exe` 把 `python313.dll` / `libcrypto-3.dll` / `_ssl.pyd` 这些映射进了内存，Windows 不允许删除被映射的文件。Inno 是**逐个文件**弹框，锁住几个就弹几次。装完还是个新旧混杂的目录 —— 跳过的是 python 运行时，缺一个就起不来。

为什么 Inno 没提前发现：`CloseApplications=no`（刻意关掉的，怕它乱关别的程序），而我们的程序是 pythonw，任务栏和窗口列表里都没有它。

**三层修法**：

1. **程序启动时创建命名互斥体** `AITeleprompterRunning`（`run.py` 的 `_hold_instance_mutex`），`[Setup] AppMutex` 在向导出现之前就能发现它 —— 只弹**一条**提示。注意 `CreateMutex` 已存在时返回 `ERROR_ALREADY_EXISTS` 但仍是有效句柄，不能当失败处理（双击两下快捷方式时第二份就走这条路）。
2. **提示文案自己写**（`[Messages] zhcn.SetupAppRunningError`）。Inno 默认只说「请关闭程序」，可 pythonw 没窗口、不在任务栏，用户根本找不到它。必须点名两条路：控制台右上角「退出程序」／任务管理器结束 `pythonw.exe`。
3. **兜底：`PrepareToInstall` 里再探一次**（`CheckAppNotRunning`）。为什么 AppMutex 之外还要这道 —— 2.2.2 及更早的版本启动时根本没创建那个互斥体，用户开着旧版装新版时 AppMutex 什么也看不见，于是又回到逐文件报错。

⛔ **两个坑**：

- **Inno 7 的 Pascal Script 没有 `FileOpen`**（编译直接报 `Unknown identifier`）。改用 PowerShell 的 `[IO.File]::Open(path, 'Open', 'Write', 'None')` —— 只打开再关掉，**不做任何写入**。绝不能用 `SaveStringToFile` 这类「顺手写点东西」的招：探测目标是 `python313.dll`，一次误截断就是「装完打不开」。实测探针跑完 md5 不变。
- **判断「程序在不在跑」不能靠 `ps | grep`**。这次它漏了 —— 没有输出，我据此以为探针误报，白查了一轮。可靠判据是 `curl --noproxy '*' http://127.0.0.1:8756/api/state` 是不是 200，或者用 Python 的 `OpenMutexW` 查那个互斥体。

实测：

| 场景 | 结果 |
|---|---|
| 程序开着，装 2.2.4 | 只弹一条「AI 提词器 正在运行…」，Setup 日志里是 `Message box (OK/Cancel)`，**一个文件都没动** |
| 程序关掉，装 2.2.4 | 3 秒铺完文件，`prep exit code 0`，`state=ok` |
| 互斥体 | 程序运行时 `OpenMutexW('AITeleprompterRunning')` 拿到句柄，错误码 0 |
| 写探针 | 程序开着 → 写打开失败；`python313.dll` 的 md5 前后一致（没被改动） |

⚠️ **测试环境的坑**（不是产品问题，但害我白跑了好几轮）：Git Bash 会把 `/VERYSILENT` 当路径改写成 `C:/…/PortableGit/VERYSILENT`，`/DIR=` 也被搅乱 —— 现象是安装器「秒退、什么也没装」，日志里 `Setup command line` 一眼就能看出来。正确写法是给**这一条命令**加前缀，不要 `export`（`export` 之后 `cmd //c` 的重写也会失效，会开出交互式命令行）：

```bash
MSYS_NO_PATHCONV=1 "dist\AI提词器-x.y.z-安装程序.exe" /VERYSILENT /NORESTART "/DIR=D:\某目录"
```

---

### 18.16 全新安装必定失败：体检的退出码被当成了错误（v2.3.0）

**现象**：装到一台**干净**的机器上，程序文件拷完，下一秒就弹「安装未完成 ——
运行环境没齐（env-check 这一步没过）」。从开始到失败只有 **1 秒**，pip 一步都没跑。

**根因**：两层约定撞在一起，而中间没有任何一处文字说明。

- `tools/check_env.py --json` 的收尾是 `return 0 if not miss_req else 1` ——
  **「缺包」返回 1**，而缺包正是全新安装的常态（torch 一个都还没装）。
  它真正的结论写在 stdout 的 JSON 里，退出码只是个顺手的人读提示。
- `tools/prep-ui.ps1` 的 `On-StageExit` 里写着 `if ($code -ne 0) { 判定失败 }`，
  对**所有**阶段一视同仁。于是第一步就判死。

**为什么一直没暴露**：之前每一次实测都是**覆盖安装** —— 目标目录里上一版的
python 依赖还在，`check_env` 返回 0，一路顺风。
**只有空目录才会踩到。** 也就是说「在旧目录上装成功」根本不能证明安装器能装。

**修法**：体检阶段把 `0` 和 `1` 都当成功；`env-verify` 仍然只认 0（那时该有的都得有了）。

```powershell
$okCodes = @(0)
if ($st.Name -eq 'env-check') { $okCodes = @(0, 1) }
if ($okCodes -notcontains $code) { ...失败... }
```

> 教训一：**用退出码表达"业务结论"的地方，必须在调用点写清楚每个值是什么意思。**
> 一个函数拿退出码说"缺不缺包"，另一处拿它说"这一步成不成"，出事只是时间问题。
>
> 教训二：**验证安装器必须用一个空目录** —— §18.8 早就写过这条，这次还是绕过去了。
> 同一个坑第二次踩，说明"知道"不等于"每次都会照做"，得把它变成操作步骤而不是记忆。

> ⚠️ 这次还重新踩了一遍 §18.15 的 Git Bash 参数改写：`/VERYSILENT` 被当成路径
> 改写掉，安装器转而**弹出图形向导**，而背景任务里没人点它 —— 表现成"退出码 0、
> 却什么都没装"。正确写法（`MSYS_NO_PATHCONV=1`）就写在 §18.15 里，隔一节就忘了。

### 18.17 安装包里只装「跑得起来」的东西（v2.4.0）

用户的原话定下了这条分工：

> 「这个安装包里记得只装软件运行需要的东西，开发流程以及一些记录之类的开源
> 则是放在 GitHub 仓库里供人能够找到并阅览就行」

也就是**两种受众、两份产物**：

| | 面向谁 | 装什么 |
|---|---|---|
| 安装包（`dist/*.exe`） | 只想装上就用的人 | 运行时 + 跑起来必需的代码，**一份文档都没有** |
| GitHub 仓库 | 想读、想改、想自己编的人 | 全部：README（中英）、`docs/` 开发记录、`tests/`、`installer/` 源码 |

所以 `INCLUDE_FILES` 里的 `README.md` 被删了（`docs/`、`tests/` 本来就不在清单里）。
**`LICENSE` 是唯一保留的"非运行时"文件** —— 那是 AGPL 的分发义务，性质上不是文档。

装完之后用户看得见的东西（`{app}` 下）：`python\` `app\` `web\` `assets\`
`tools\` `run.py` `requirements.txt` `LICENSE` `start.bat` `VERSION.txt`
`data\` `models\` `_tmp\`。其中：

- `tools\` 四个脚本**看着像开发工具，其实都得留**：`download_model.py`（装完还能手动补下载）、
  `pip_progress.py`（安装器靠它跑 pip 并回报百分比）、`check_env.py`（增量安装的全部依据）、
  `prep-ui.ps1`（进度窗口本体）。它们和"开发流程记录"不是一类东西
- `start.bat` 是开始菜单里那条「排障启动」快捷方式的目标（见 iss `[Icons]` 第 178 行），
  不是给开发者的
- **文档去哪儿找**：不需要塞进安装目录 —— iss 的 `AppPublisherURL / AppSupportURL /
  AppUpdatesURL` 都指向 `https://github.com/BBsaba/ai-follow-teleprompter`，
  Windows「应用和功能」里的支持链接点一下就到仓库

#### ⛔ 顺手修掉一个比"清单写错"更隐蔽的坑

`copy_project()` 原来只**往里拷**、从不清理旧文件。于是「从清单里删掉一个文件」
根本不会让它从包里消失 —— 上一版打进去的 `README.md` 会继续躺在 `build/payload/`
里，被 `[Files]` 的 `Source: {#PayloadDir}\*` 原样扫进去。**清单看着减了，包里没减。**

改成每次拷贝前先清空 payload（只保留 `python/`，那是 `--skip-runtime` 要复用的）：

```python
for p in PAYLOAD.iterdir():
    if p.name == "python":
        continue
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
```

> 教训：**"打了个新包"不等于"包里只有新清单里的东西"。** 增量式的拷贝脚本必须
> 自带"清空重来"，否则清单是愿望、目录才是事实。判断包内容时别读清单，
> 去 `ls build/payload`，或者看 ISCC 编译日志里那串 `Compressing:` 列表。

**v2.4.0 实测**：`AI提词器-2.4.0-安装程序.exe` **13.0 MB**（比 2.3.0 小 2.9 KB，
正好是去掉 README 的量级）；`build/payload` 顶层只剩 `LICENSE VERSION.txt app
assets python requirements.txt run.py start.bat tools web`；ISCC 日志里
没有 `README.md` 这一行。

---

## 19. 退出程序：pythonw 没有窗口可关（v2.2.3）

快捷方式走 `pythonw.exe`，好处是不弹黑框，代价是**没有窗口可关**：用户关掉浏览器标签页，服务还在后台跑，想停只能去任务管理器里找 `pythonw.exe`。这不是正常用户该做的事。

控制台右上角因此多了一个「退出程序」（红色，和旁边的「打开提词窗」明确区分开）。

**链路**：`web/console.js` → `POST /api/quit` → `app/shutdown.py` → 置位 `uvicorn.Server.should_exit`。

几个刻意的选择：

- **不用信号**（`os.kill` / `signal.raise_signal`）。信号处理器只在主线程装得上，而且 Windows 的 `CTRL_C_EVENT` 只对控制台进程组有效 —— 我们最需要它工作的那种情况（`pythonw` 无控制台）根本送不进去。直接置位 uvicorn 自己的旗子，与有没有控制台无关。
- **run.py 自己建 `uvicorn.Config` + `Server`**，不再调 `uvicorn.run()`。行为完全一样（`uvicorn.run()` 内部就是这两步），区别只是那个 `Server` 对象我们能拿到，`bind` 进 `app/shutdown.py`。为什么单开一个模块：`Server` 在 run.py 里创建，`/api/quit` 在 app/server.py 里，直接互相 import 会成环。
- **必须用 `BackgroundTasks`**，不能直接在处理函数里退。Starlette 保证后台任务在响应发完之后才跑。早先直接调过一次，实测服务退得太快、连接被掐断，浏览器只拿到网络错误 —— 用户点完按钮看到「出错了」，以为没退成功。
- **点按钮前先把稿子存盘**（`await saveScript()`）。退出会掐掉服务，还在等 800 ms 防抖的那次自动保存就没了。
- **退出后盖一层遮罩**。接口全没了，留一堆点不动的按钮只会让人以为卡死。遮罩上写明「服务已停了，这个标签页可以关掉；下次要用双击桌面上的 AI 提词器」。
- **4 秒后复查一次**「是不是真的退了」。优雅退出要跑 lifespan 的 finally（关音频流、等识别线程收尾），万一卡住，用户会看到「已退出」却还能刷新出界面 —— 那是最糟的一种谎话。复查还活着就直接说「退出没有生效，请到任务管理器结束 pythonw.exe」。
- **`shutdown.py` 里有 8 秒硬退兜底**（`os._exit(0)`），防止优雅退出卡住导致「点了没反应」又回来。

实测（2.2.4）：

| 步骤 | 结果 |
|---|---|
| 点桌面快捷方式 | `/` 200、`/api/version` 返回 2.2.4、页面里有 `btnQuit` |
| `POST /api/quit` | HTTP 200，响应体 `{"ok":true,"quitting":true}`（先回话再收摊） |
| 退出后 | 端口立即关闭，进程消失 |
| 再点快捷方式 | 照常启动，200 |

**顺带把版本号收成一处**：控制台标题原本硬编码 `v2.0`，每次发版都要记得改第二处，迟早不一致。现在服务端读 `VERSION.txt`（构建脚本写的）并通过 `/api/version` 给出，前端只负责显示。源码目录没有这个文件时报 `dev`。

---

## 20. 源码版的快捷方式：怎么让 `make_shortcut.py` 也不弹黑框

**问题**：`tools/make_shortcut.py` 从第一天起就指向 `start.bat`。`start.bat` 是个批处理，
双击**必然**先开一个 `cmd.exe` 窗口 —— 于是同一台机器上出现两种体验：安装版双击没黑框，
源码版双击一个黑框杵在那儿。用户会以为"源码版比较落后"，其实只是快捷方式指错了东西。

**为什么当初指向 bat**：v2.2.1 之前，`pythonw` 下 `run.py` 根本跑不起来（`sys.stdout` 是
`None`，uvicorn 初始化第一步就抛异常，见 §18.14）。那时只能靠 `start.bat` 里的
`pause` 把报错留在屏幕上。**v2.2.1 把这个问题修好之后，这个妥协就该撤掉了，但没人回头改。**

**修法**：

- 默认目标改成 `pythonw.exe` + `run.py`，工作目录仍是工程根
- 保留 `--with-console`，指向 `start.bat` —— 开发时看得见 traceback，这个需求是真的
- 找解释器的顺序和 `start.bat` 对齐：`.venv\Scripts\pythonw.exe` → `%TELEPROMPTER_PYTHON%`
  旁边的 `pythonw.exe` → 当前解释器旁边的 → 都找不到才退回 `start.bat` 并打一行警告
- 新增 `--show`：把现有 `.lnk` 的 target / arguments / working_dir / icon 读回来打印。
  「为什么双击跑的不是我想的那个 python」这类问题，一条命令就能定位

### 20.1 为什么不用 pywin32，也不用自己拼 .lnk

`win32com.client.Dispatch("WScript.Shell")` 要装 pywin32（10 MB），而**只为了建一个 600 字节的快捷方式**。
新增的 `tools/win_shortcut.py` 用 `ctypes` 直接对着 COM 虚表调 `IShellLinkW` / `IPersistFile`，
标准库就够，`requirements.txt` 一个字都不用加。

为什么**不**自己按 MS-SHLLINK 手拼二进制：那个格式要求同时给出 `LinkTargetIDList` 和
`LinkInfo`，少一个字段资源管理器就把快捷方式显示成「未知项目」。走系统 API 让 shell 自己
生成，结构一定对。

虚表下标是固定值，写死在模块里（`IShellLinkW`: 7 SetDescription / 9 SetWorkingDirectory /
11 SetArguments / 15 SetShowCmd / 17 SetIconLocation / 20 SetPath；`IPersistFile`: 5 Load / 6 Save）。

⛔ **三个 ctypes 上的坑**（都实际卡住过）：

| 坑 | 现象 | 正解 |
|---|---|---|
| `HRESULT` 子类不能位运算 | `hr & 0xFFFFFFFF` 抛 `TypeError` | 先取 `.value` 再转 `int` |
| `int(c_long)` 拿不到值 | 同上，`int(hr)` 也报错 | `int(getattr(hr, "value", hr))` |
| **子类实例和 int 直接比较不可靠** | `CoCreateInstance` 明明 `S_OK`（值 0），`if hr != 0` 却判成不相等，误报失败 | 一律 `_v(hr) != S_OK`，先转 int 再比 |

### 20.2 ⚠️ 验证「无控制台」不能用 bash 启动

这是本轮最容易自我欺骗的一步。**从 bash 里 `./pythonw.exe run.py &` 启动，验证不出真实现象** ——
进程继承了 bash 的 stdout/stderr 管道，`sys.stdout` 不是 `None`，`_ensure_streams` 走"有控制台"
分支，`launch.log` 里会写**「控制台 有」**。看着"跑通了"，其实测的是另一条路。

真双击时进程没有任何标准句柄。**正确做法是让 shell 替你启动**，也就是双击走的那条路：

```python
import ctypes
ctypes.windll.shell32.ShellExecuteW(None, 'open', r'C:\...\AI提词器.lnk', None, None, 1)
# 返回值 > 32 表示成功
```

实测（v2.2.4 源码版）：

| 检查项 | 结果 |
|---|---|
| `ShellExecuteW` 返回值 | `42`（>32，成功） |
| `data\launch.log` 第一行 | **`控制台 无（pythonw）`** ← 走对了分支 |
| `/` | 200 |
| `POST /api/quit` | `{"ok":true,"quitting":true}`，随后端口 000 |
| 黑框 | 没有 |

对照：bash 直接起 —— `launch.log` 写「控制台 **有**」，说明测的不是同一件事。

### 20.3 顺带修掉两句过期文案

`run.py` 里 `pythonw` 分支原本打印「要停止请在任务管理器结束 pythonw.exe」，
另一处打印「要重启请先关掉旧窗口」—— 两句话都是 v2.2.3 之前的现实。
现在停止是控制台右上角的「退出程序」，且 `pythonw` **没有窗口可关**，"关掉旧窗口"
会让人满屏幕找一个不存在的窗口。已改为：

- `后台运行：没有控制台窗口。停止请用控制台右上角的「退出程序」。`
- `要重启：在控制台页面右上角点「退出程序」，然后再打开一次。`

> 教训：**新增一个替代性机制（退出按钮）之后，要把所有描述旧机制的文字搜一遍。**
> `grep -n "任务管理器" run.py app/*.py web/*.js` 一秒钟的事，拖了两版才发现。

---

## 21. 跟读跳读：限「范围」，不是限「速度」（v2.4 定稿）

这一节记了**四个版本**。前三个都在「速度」这个维度上打转，全错；
第四个才回到问题本身：用户要的是**不许去太远**，不是**去得慢一点**。

### 21.1 四次投诉，四个病根

| # | 用户原话（节选） | 真正的病根 |
|---|---|---|
| 1 | 「上下文有些重复的部分会导致提词器大幅度的上下滚动」 | 一拍之内锁到远处副本（终点自由，最远 100 字） |
| 2 | 「设了限位一行，读稿时一下跨五行六行都会直接跟过去」 | 限的是「单拍位移」，而 ASR 分拍送 → 夹子从不触发 |
| 3 | 「跳到第七行还跟，跳到第八行就不跟了」 | 搜索窗口只看到 100 字，每行 20 字 → 5 行就是边界 |
| 4 | 「并非按每秒多少行限位……跳得太远的部分不跟」 | 维度错了：这是**距离**问题，不是**速度**问题 |

前三次看起来像同一个毛病，其实一次比一次深：落点 → 量纲 → 锚点。第四次直接换了维度。

### 21.2 ⛔ 第一版：限「拍」等于没限

```python
limit = self.max_jump_lines * self.script.per_line      # 5 × 14 = 70 字
new_pos = max(self.pos - limit, min(self.pos + limit, new_pos))
```

实测复现，**限 1 行和不限，轨迹一模一样**：

```
每拍喂 20 字、连喂 6 拍（共 120 字 ≈ 6 行）
不限   ：[20, 40,  60,  80, 100, 120]
限 1 行：[20, 40,  60,  80, 100, 120]     ← 夹子一次都没触发
```

**根因：量错了对象。** ASR 是 **3 Hz** 一小段一小段送进来的，每拍只有 10–20 字。
用户「一下跨 5-6 行」是分 5~6 拍送到的，每拍都不到 1 行（20 字）的阈值。

> ⛔ 「一拍（0.33 秒）」在用户那里根本不可感知。所有跟「快慢」有关的参数，
> 量纲必须是**时间**，不能是**帧/拍**。

### 21.3 ⛔ 第二版：按秒限速 + 追赶加速

按 `dt` 发额度，方向对了，但配了个 `boost = min(1 + starve*0.5, 3.0)`。
实测设 2 行/秒（40 字/秒）时实际跑出 **120 字/秒** —— 跳 5 行本该 2.5 秒，
实际 1.65 秒。用户体感"唰地跟过去"，和第一版投诉的是同一句话。

> ⛔ **滑块的值必须等于真实速度。** 任何"智能加速"都会让设置和体感对不上。

### 21.4 ⛔ 第三版：锚点与显示分开

用户第二次验收时出现「一半跟、一半不跟」。探针（锚点固定，只喂远处一句）：

| 目标离锚点 | 80 字 | **100 字** | 120 字 | 140 字 |
|---|---|---|---|---|
| conf | 1.00 | **0.37** | 0.43 | 0.48 |

`lookahead = 100`，而窗口锚在**被限速夹住的 `pos`** 上 —— 夹得越紧，窗口离人越远。
于是拆出 `raw`（真实位置，不受限速）与 `pos`（显示位置），窗口锚 `raw`，
再加一层远窗接住大跳。

**这一版治好了「第 8 行」，但仍在限速度。** 于是：

- 跳 5 行、设 2 行/秒 → 屏幕**缓缓滑过去 4 秒**。用户看到的就是"它还是跟过去了"
- 用户为了不跟，只能把速度调到 1 行/秒 → 跳 8 行要 32 秒，正常读又会被拽住

### 21.5 ⭐ 第四版（定稿）：用户要的是距离，不是速度

原话：

> *「并非按照每秒多少行来进行限位，而是就利用这个仅识别 ±140 字的机制，让用户可以自行调整范围，
> 防止有时候提到的一些词语与很多行以后的内容重合一下跳一大段，是这个目的，跳的太远的部分不跟」*

这句话把前三版共同的错误点点破了：**速度是"去得多快"，用户要的是"该不该去"。**
按速度限，它照样会去，只是慢 —— 而"慢"在屏幕上表现为"画面在滑"，比"不动"更让人困惑。

而「范围」根本不需要额外造一个闸：**它本来就在搜索窗口里。** 窗口收窄，
窗外的匹配**根本进不了候选**，一步都不用走。

于是整套限速机构全部删掉：

| 删掉的东西 | 为什么删 |
|---|---|
| `_rate_limit` / `_budget` / `_last_t` | 没有速度概念了，一拍到位 |
| `raw` / `pos` 双位置 | 没有限速就没有"追"的过程，一个位置够了 |
| 远窗候选 + 连中两拍 | 用于"接住大跳"，现在大跳**本来就不该接** |
| boost / 迟滞 / 兜底 | 都是给速度限位打的补丁 |

### 21.6 实现：窗口即范围

```python
def radius(self) -> int:
    per = int(self.script.per_line) or 1
    return max(self.follow_lines * per, MIN_LINES * per, MIN_RADIUS)

def window(self):
    r = self.radius()
    return r, r                      # 前后各 N 行（有下限，见下面第 ④ 条）
```

一拍的处理顺序：

| 步 | 做什么 | 为什么 |
|---|---|---|
| ① | 在 `pos ± N 行` 里 DTW | 正常跟读全走这条 |
| ② | 近窗 `conf < 0.62` 时，再开一个 `max(3N, 400)` 字的**侦察窗** | 判断"人是不是在范围外" |
| ③ | 侦察窗里「明显更像」（好 0.10 以上）→ **这拍不跟**，并记下差多少字 | 这是"跳太远"，要说出来 |
| ④ | 否则采纳近窗结果 | 范围内的跳读**一步到位** |

四个坑，都在实测里踩过：

**① 侦察窗只能用来判断，绝不能用它落点。** 它存在的唯一目的是回答
"外面是不是有个明显更像的地方"。如果拿它的结果去落点，就等于把范围放大了 3 倍。

**② 侦察半径必须有下限（400 字）。** 范围调到 2 行时 3 倍只有 84 字，
连"撞车"都够不着 —— 用户看到的就是"不跟、也不说为什么"，正是前三版被投诉的体验。

**③ 平局必须偏向近处（`NEAR_BIAS`）。** 稿子里同一句话出现两次时，两处 DTW 代价
**完全相等**，选谁取决于插入顺序。实测会选到靠前那份，屏幕"啪"地往回跳一大段 ——
这正是用户最初投诉的形态。给「离当前位置远」的候选每个 token 加 0.001 的代价，
让近的赢；这个数必须远小于一次替换代价（0.35），否则会盖过真实的匹配差异。

**`over` 必须回报给界面。** 不报的话，用户只看到屏幕忽然不动了 ——
"静默地不跟"正是前几轮反复被投诉的那个体验。控制台拿 `over` 显示
「超出跟随范围 · 差 N 行 · 拨滚轮或调大「跟随范围」」。

**④ 半径有下限：`max(N × per_line, 3 × per_line, 40)` 字。**
这条是**加完代码之后实测才发现的**，不是预防性设计：

| 范围（每行 20 字） | 半径 | 每段 10 字 | 每段 20 字 | 每段 30 字 | 每段 40 字 |
|---|---|---|---|---|---|
| 1 行 | 20 字 | ✓ 901/900 | ✓ 901/900 | **✗ 20/900** | **✗ 0/880** |
| 2 行 | 40 字 | ✓ | ✓ | ✓ 901/900 | ✓ 880/880 |
| ≥3 行 | 60+ | ✓ | ✓ | ✓ | ✓ |

（✓ 后面的两个数是"跟到 / 喂到"，正常应当相等。）

原因：识别结果**一段话是 20~40 字**。半径比这句话还短时，窗口装不下整句，
DTW 只能把 q 的尾巴逐字走 `gap_asr`（每个 0.85）硬挤在窗口边缘 —— 30 字的 q
挤 10 个只花 8.5 的代价、置信度算出来还有 0.72，于是它**"成功"匹配到窗口边缘**，
而真实位置在窗口外。下一拍再重复一次，位置永远差一截、永远够不到 →
**跟读彻底停摆**。

更阴的是：停摆时 `delta` 一直是 0，可 `over` 也一直是 0（从来没触发侦察），
界面报不出任何原因 —— 用户看到的就是"跟读坏了"，而不是"范围设太小了"。
所以下限必须存在，并且 `follow_lines_min` 直接定成 **3**（不是 1），
让用户根本调不到会坏的档位。

**⑤ 窗口截断不算匹配：`end == len(P) and skips >= 2` 时这一拍作废。**

这是**第五次返工的真正病根**（2026-11-21，用户报「限制在三行，还是从开头跳到了
第七行，到第八行反而不跟了」）。诊断链条：

1. 4 秒滑窗每 0.3 秒重算一次，**相邻两拍重叠 95%**，所以"两拍"只隔 0.6 秒，
   用户看到的就是"一下子跳过去了"，根本没有中间过程可察觉。
2. 跳读那一刻，滑窗里**同时装着"刚才念的"和"现在念的"**：前半句在窗口内，
   后半句在窗口外 —— 这是真实语音，不是测试构造。
3. DTW 必须把 q 走完，装在窗外的部分只能逐字 `gap_asr`（0.85/字）。而窗内有的是
   同音近音字，那些字并不是整齐地丢在结尾，而是**散在路径中间被"捡"回去匹配掉**，
   所以「数结尾连续跳了几个字」根本数不出来（实测只有 5，而门槛是 11）。
4. 于是代价不高、置信度还有 0.6~0.9 → **被当成一次成功匹配**，落点恰好在窗口边缘。
5. 窗口边缘跟着 `pos` 一起走：这一拍贴到 +42，下一拍真目标（+82）距新位置只有 40，
   落进窗口 → 接受。**两拍走完 6 行，而 `over` 全程是 0，界面什么都不报。**

判据不能只数"跳了几个字"：正常跟读碰上 ASR 噪声也能跳到 5~6 个（1200 条带噪声
实测：阈值 3 误挡 29%、阈值 5 误挡 1.4%、阈值 6 仍误挡 0.3%），而跨窗片段最小
也是 6 —— 两堆数在 6 上正面撞车，绝对阈值怎么定都有错。

真正干净的特征是**路径终点顶在窗口最后一格**：人的下一句已经在窗外，DTW 无处
可去，只能贴边收尾；而正常跟读即使噪声大到跳 6 个字，落点仍在真实位置、离窗口
末尾还有十几格。实测 600 条带噪声正常跟读 **0 条**贴边，2352 条跨窗片段 **100%**
贴边，`end == len(P) and skips >= 2` 误挡 0、漏网 0。

⚠️ 必须带 `hi < n` 这个条件：窗口撞到**稿子末尾**时那不是范围边界，人真的就在
最后一个字上，落点贴边是对的。少了它，念到最后一句会突然不跟。

⚠️ 这条与 ④ 是**同一枚硬币的两面**：④ 说的是"窗口装不下这句话 → 跟读停摆"，
⑤ 说的是"窗口装不下这句话 → 假装跟上了"。两者都源于"DTW 可以靠 `gap_asr`
把装不下的部分糊过去"，一个表现为不动，一个表现为乱动。所以修 ④ 用**加下限**，
修 ⑤ 用**认出来并作废**，缺一个都不行。

### 21.7 参数

`config.DEFAULT_UI` 三个键：`follow_lines=8` / `_min=3` / `_max=50`。
**单位是「行」**，不是「字」也不是「行/秒」—— 用户看到的是行，调的是行；
实际半径 = `max(N × per_line, 3 × per_line, 40)` 字，所以改「每行字数」时
范围跟着变宽，符合直觉。

| 值 | 含义 | 每行 20 字时的实际半径 |
|---|---|---|
| 3 | 最紧（下限档），跳三行以上就不认 | ±60 字 |
| 8 | 默认 | ±160 字 |
| 20 | 松 | ±400 字 |
| 50 | 基本不设防 | ±1000 字 |

**为什么默认 8**：正常朗读时每拍只前进 5 字左右，8 行（160 字）远远够用；
而"和十几行以后的内容撞车"正好被挡在外面。

**面板必须把字数写出来**（`8 行 · 160 字`）。"设置和实际体验不符"是这个功能
被返工四次的直接原因；把实际生效的半径摆在滑块右边，是最便宜的对齐手段。
⚠️ `web/console.js` 里的 `jumpRadius()` 必须和 `Aligner.radius()` 逐字一致，
改一边就得改另一边 —— 否则面板上的字数又变成了一句谎话。

> ⚠️ 键名换了（`max_jump_lines` → `follow_lines`），`store.load_state()` 里会把
> 退休的键从老 `state.json` 里清掉。**别复用旧名**：同名不同义（行/秒 → 行）
> 会让老用户的 `2` 从"每秒 2 行"变成"只许 2 行范围"，一升级就废。

界面：控制台第 5 个滑块，显示 **`N 行 · M 字`**。
它和「速度」滑块构成一对：一个亮一个灰，本身就说清了当前哪个模式在起作用。

> ⚠️ 控制台滑块那一栏的 `grid-template-columns` 是 `56px 1fr 100px`：
> "跟随范围"四个字在 42px 里放不下，会压到滑块上；第三列不到 100px 的话
> `50 行 · 1000 字` 会折成两行、把五行滑块的行距撑歪。以后再加四字标签先看这一列。

### 21.8 验收（实测）

1400 字长稿、20 字/行、范围 8 行：

| 场景 | 结果 |
|---|---|
| 正常匀速跟读 30 拍（15 字/秒） | 应到 150，实际 150，**偏差 0**；每拍 0.3 ms |
| 读到某词、和 15 行后撞车（2 拍） | `delta=0`，`over=+14.5 行`，位置一点没动 |
| 范围内跳 4 行 | `delta=75`，conf 1.00，**一眼跟上** |
| 范围外跳 12 行 | `delta=0`，`over=+11.8 行`，位置不动 |
| 连续 5 拍都在范围外读 | 位置始终没被拖走（不会漂到窗口边缘） |
| 重复句、两处都在范围内 | 选了**近的那份**（没有 `NEAR_BIAS` 时会跳回远处） |
| 范围旋钮 | 3/4/8 行 → 12 行跳读不跟；16/30 行 → 跟。单调 |
| 侦察窗开启时的每拍耗时 | 1.7 ms（范围 2 行、目标在 20 行外） |

半径下限（每行 20 字，逐段喂 900 字，看"跟到 / 喂到"）：

| 半径 | 每段 10 字 | 20 字 | 30 字 | 40 字 |
|---|---|---|---|---|
| 20 字（旧的下限） | 901/900 | 901/900 | **20/900 停摆** | **0/880 停摆** |
| 40 字 | 901/900 | 901/900 | 901/900 | 880/880 |
| 60 字（现在的最小档） | 901/900 | 901/900 | 901/900 | 880/880 |

其它：

- `follow_lines=0` → 退回 `lookback/lookahead` 固定窗口，单测与裸用法不受影响
- 改「每行字数」→ 搜索半径跟着变（14 字/行 × 6 行 = 84；20 字/行 × 6 行 = 120）
- `test_ws` / `test_ui` 里也要跟着改键名，否则前端拿不到滑块初值

### 21.9 ⛔ 改完键名用户却看到 `undefined`：静态资源被缓存了

**事故（2026-11-21 18:00）**：范围限位验收通过后，用户发来截图 ——
滑块标签还是「最大跟进」，数值变成 **`undefined 行/秒`**。

查下来：**后端是新版**（`/api/state` 里只有 `follow_lines`），
**页面里跑的是旧版 JS**（`fmtJump = v => \`${v} 行/秒\``，读已退休的 `max_jump_lines`）。

根因：`StaticFiles` 只发 `ETag` / `Last-Modified`，**没有 `Cache-Control`**。
Edge 会按"启发式"自行决定缓存多久，于是那个从早上就开着的标签页
一直跑着 v2.3.x 的 `console.js`。

**两层修法（缺一不可）**：

| 层 | 做什么 | 管什么 |
|---|---|---|
| 服务端 | 页面 / `.js` / `.css` / `.html` / `/api/*` 一律 `Cache-Control: no-cache, must-revalidate` | 刷新一次就一定拿到新文件 |
| 前端 | `/api/version` 增加 `web` 指纹（`web/` 下文件的最大 mtime）；页面每 5 秒 + 每次切回标签页比对一次，不一致就在底部亮提示条 + 刷新按钮 | 已经开着的页面也能发现自己过期了 |

**为什么不自动刷新**：用户可能正在编辑器里敲字，`location.reload()` 会吞掉
还没发出去的几个字符。给一个"刷新页面"按钮，点不点他自己定。

**顺手加的防御**：`console.js` 里所有从后端读来的数字都过 `numOr()`，
不认识的值显示 `—` 而不是 `undefined`。**界面上永远不该出现 `undefined`** ——
它一定会被当成"程序坏了"报上来。

> 📌 教训：**只要动了 `config.DEFAULT_UI` 的键名，就必须保证前端也会被换掉。**
> 本地程序的静态资源缓存看起来"不可能出错"，恰恰最容易出错。

### 21.10 窗口截断判据的标定数据

判据要回答的问题是：**这个位移该不该认。** 所以先造两堆样本，看哪个数字能把它们
分开。

三堆样本（1400 字稿、每行 14 字、半径 42 字）：

| 堆 | 怎么造 | 期望 |
|---|---|---|
| A 正常跟读 | 从 `pos-4` 念到 `pos+{10..26}`，再叠 ASR 噪声（插 0~3 字 / 替 0~6 字 / 删 0~3 字） | **全部通过** |
| B 跨窗片段 | 从 `pos-{0,4,6,8}` 一直念到 `pos+{45..120}` | **全部挡住** |
| C 纯窗外跳读 | 整段都在 `pos+{80,100,130}` | 挡住（本来就会被 `min_conf` 挡掉） |

「只数跳过几个字」的失败现场：

| 阈值 | A 通过 | B 挡住 | C 挡住 |
|---|---|---|---|
| 3 | 370/370 | 444/444 | 209/222 |
| 6 | 370/370 | 444/444 | 113/222 |
| 8 | 370/370 | **382/444 ✗** | 40/222 |

A、B 在阈值 6 上撞车 —— **绝对字数根本不是一个可用的判据**。
（`skips` 的分布：A 的 p50/p90/max = 2/3/5，B 的 p50/max = 23/73，看起来分得很开，
那是均匀采样骗人；一上噪声，A 的长尾就顶到 B 的下沿。）

换「终点是否贴边」之后：

| 判据 | A 误挡 | B 漏网 |
|---|---|---|
| `end == len(P)` | 0/600 | 0/2352 |
| `end == len(P) and skips >= 2` | **0/600** | **0/2352** |

⚠️ 加 `skips >= 2` 是为了给"人正好站在范围边界上"留 1 个字的余量 ——
因为单独一条 `end == len(P)` 在边界上会误伤。

⚠️ 这里的 `skips` 必须数**整条路径**上跳过的识别字，不是"结尾连续跳过"。
第一版数的是结尾连续的，实测跨窗时只有 5（门槛 11）就放过了 ——
因为 DTW 把挤不下的字散在路径中间"捡"回来匹配掉了。这个坑花了一整轮才定位到。

验收（用户原稿，每行 14 字 / 160 行，范围 3 行）：

| 场景 | 结果 |
|---|---|
| 从头顺读 139 拍到底 | 每拍 Δ+14，conf 1.00，**0 误挡** |
| 片段从 0/20/40/60/70 长到 +82/+92/+102（15 种组合） | **0 种跟过去**（修之前是 33 种） |
| 跨窗片段 16 种跨度（单测 `test_range_straddle`） | 动了 **0** 种 |
| 念到最后 22 个字 | 照常跟到稿尾（`hi < n` 那条起作用） |
| 单测 | `test_align` 71 通过 / 0 失败；全套件 285 通过 / 0 失败 |

**有没有让跟读变卡？** 连续 886 拍（每拍前进 1 字，模拟 `hop_sec=0.3`）对比：

| 噪声档位 | 判据开 → 卡住的拍 | 判据关 → 卡住的拍 |
|---|---|---|
| 无噪声 | 95 | **95** |
| 插入 2 / 替换 4 / 删除 1 | 184 | **184** |

一个不差 —— 说明卡顿全部来自"一拍只前进 1 字、DTW 落点量化到同一个字"这个固有
特性，**新判据贡献 0**。终位误差 0~1 字。

> ⛔ **副作用要知道**：截断判据把"贴边爬行"这条**顺带的重锚路径**也一起堵死了。
> 以前人跳到范围外，靠两拍贴边就能"蹭"过去；现在位置会**一直不动**，控制台报
> 「超出跟随范围 · 差 N 行 · 拨滚轮或调大「跟随范围」」。
> 这是用户明确要的行为（「跳读第七行不该跟进」），但也意味着**真跳过一大段之后
> 必须手动拨滚轮**（一格一行，`Session.wheel()` 会把对齐器锚点一起挪）。
> 没有做"连续几拍都在范围外就自动接受"：`hop_sec=0.3`、相邻两拍重叠 95%，
> 一个词的撞车就能连报三五拍，"连续 N 拍"根本区分不出"手滑"和"真的走远了"。

---

## 22. 磁盘卫生：程序自己不写临时文件，但日志会一直长（v2.3.0）

### 22.1 先回答那个担心

用户问：*「软件运行时会不会出现一些临时文件？我担心没有退出时自动清理，会越来越臃肿」*

把仓库里所有写盘的位置查了一遍（`grep -rn "open(\|write_text\|tempfile" app/ run.py`）：

| 位置 | 写什么 | 会不会越长越大 |
|---|---|---|
| `data/scripts/*.md` | 你的稿件 | 只随稿件数量增长 —— **这是资产** |
| `data/state.json` | 界面设置 | 每次覆写，不增长（几百字节） |
| **`data/launch.log`** | 每次启动追加 | ⚠️ **只追加，以前永不轮转** |
| **`%TEMP%\AITeleprompter-launch.log`** | 同上（装到不可写目录时的退路） | ⚠️ 同上 |
| `app/__pycache__/` | 字节码 | 有界，跟源码走 |
| 安装目录 `_tmp/`、`is-*.tmp` | 安装过程 | 装完不一定清干净 |

**结论：程序里没有用 `tempfile`、不录 WAV、不缓存音频。** 麦克风数据全在
`listener.py` 的环形缓冲里（内存）。所以不存在"录一次多一堆文件"。

真正会无上限增长的只有 `launch.log`，它长得很慢（约 500 B/次启动），但**没有上限**。

### 22.2 日志轮转

- 超过 **512 KB** → 改名成 `launch.log.1`（覆盖旧的），只留一份，总占用上限约 1 MB
- `%TEMP%` 那份用**同一张表**（`config.LOG_FILES`）：`app/storage.py` 的「数据占用」
  和「清理日志」按它算。⛔ 只加一处，就会出现"面板显示没日志、实际 %TEMP% 里躺着一个"
- `run.py` 的 `_ensure_streams` 和文件末尾那个**崩溃兜底**共用 `_open_log()`

⛔ **顺序：先 rename，再 `open("a")`。** 反过来，文件正被自己占着，Windows 上
rename 会 `PermissionError`，然后被 `except OSError` 吞掉 —— 看上去"加了轮转但文件
还在长"，是最难查的那一类"没效果"。同理，两处各写一套 `open("a")` 迟早漏一处，
所以崩溃兜底也走同一个函数。

### 22.3 `_tmp` 的真相：它是 pip 下载缓存，而且以前只在卸载时删

`installer/AI提词器.iss` 的 `TmpDir := AppDir + '\_tmp'`，里面装的是：

- `pipcache/` —— prep-ui.ps1 用 `--cache-dir` 指过来的 pip 下载缓存，**torch 一个包就 240 MB**
- `progress.txt` / `cancel.flag` / `pause.flag` / `prep-result.txt` —— 安装过程的进度与标志

**v2.3.0 之前只有 `CurUninstallStepChanged` 会删它** —— 也就是说装完之后它一直躺在
安装目录里，直到用户卸载。实测过的残留 `is-*.tmp` 也是同一类问题。

修法分两处，**故意不同**：

| 位置 | 删什么 | 为什么 |
|---|---|---|
| 安装器（`CurStepChanged` 末尾，仅 `DepsReady` 时） | 整个 `_tmp` | 装成了，下载缓存就作废了。失败/取消时**保留** —— 用户多半要重跑，能接着下 |
| `run.py` 启动（`sweep_startup_junk`） | `is-*.tmp` + 那四个进度/标志文件 | ⛔ **不碰 `pipcache`** |

> 规划原来写的是"run.py 启动时把 `_tmp` 也清一遍（双保险）"。**实测后改成不清**：
> `_tmp/pipcache` 是"重新运行安装程序补依赖"时唯一能省下 240 MB 的东西，
> 程序没资格替用户扔掉它。要回收请走设置页的「数据占用」面板 —— 那是用户的决定。

### 22.4 控制台「数据占用」面板（设置页）

四行固定 + 一行「安装缓存」（只在它真占地方时出现）。**只统计、只显示，不自动删**。

```
稿件        4 篇      11.0 KB
日志        1 个        2.0 KB   [清理]
语音模型    1 个        1.8 GB
程序本体    —           1.6 MB
合计                    1.8 GB
```

- 四行互不重叠：稿件 ⊂ data，日志 ⊂ data，模型 ⊂ models，
  程序本体 = 安装目录 **减掉** `data` / `models` —— 所以 `total` 就是它们相加
- 「程序本体」还跳过 `.git` / `.venv` / `dist` / `build` / `node_modules`：
  那些**只在源码目录里存在**，不跳的话开发者会看到"程序本体 1.3 GB"，那是他的 venv
- 统计走线程池（`run_in_executor`）：模型目录几万文件，在事件循环里数会把
  60 Hz 心跳卡住，表现为画面一顿一顿。实测本机 `scan()` **3 ms**
- `POST /api/storage/clean` 只认白名单 `storage.CLEANERS = {logs, install_cache}`。
  ⛔ **传 `scripts` 一律 400**。白名单比黑名单可靠：将来 storage 里多一个清理函数，
  不会因为漏配一个 `if` 就变成能从浏览器调用的删除器

### 22.5 清理日志时那个"删不掉的自己"

当前进程的 stdout 就挂在 `data/launch.log` 上，Windows 删不掉被打开的文件。
`clean_logs()` 于是退一步**清空**它：Python 的 `"a"` 带 `O_APPEND`，每次写都先
seek 到末尾，所以清空之后日志从 0 字节重新长，**不会留一个巨大的空洞**。
实测：100 B 的日志被清空后，同一个句柄再写一行 → 文件 17 B，内容正确。
接口返回值 `{deleted, truncated, failed}` 逐项说清每个文件的下场。

### 22.6 ⛔ 三条边界（明确不做）

- **不自动删 `data/scripts/*.md`。** 那是用户资产，误删一次就够致命。`storage.py`
  里连一个"清理稿件"的函数都不该出现
- **不做定期清理任务**（计划任务 / 常驻服务）。为 1 MB 日志引入后台进程不值得
- **不把日志藏起来**。出问题时它是唯一线索，"眼不见为净"等于把排障能力删了

### 22.7 验收（实测）

- 把 `launch.log` 灌到 **900,000 B** 再模拟 pythonw 启动 → 轮转成 `launch.log.1`
  （900,000 B 原样保留），新 `launch.log` 只有 **268 B** 的启动头 ✅
- 故意崩一次（`TELEPROMPTER_PORT=abc`）→ 完整 traceback 写进日志（268 → 694 B）✅
- 面板数字与 `du` 一致：稿件 4 篇 11,275 B、模型 1,880,618,215 B ✅
- 浏览器点「清理」→ `删掉 launch.log`，稿件一篇不少 ✅
- `tests/run_all.py --fast`：**249 通过 / 0 失败（6 个文件）**，v2.2.4 时是 194 ✅

---

## 23. README：配图怎么拍、中英两份怎么同步（v2.4.0）

README 里那四张图是脚本拍的，不是手截：`D:\WorkBuddy\temp\shot_readme.py`
（不进仓库 —— 它依赖本机 playwright 和一份正在跑的服务）。

拍图只有一个硬指标：**每张图都必须能让读者看见正文里的那句话**。所以下面几条不是技巧，是前提。

### 23.1 为什么拍照时要临时改 `per_line` / `font_px`

用户机器上是每行 **19 字 / 64 px**（他自己调顺手的手感），但 19×64 = 1216 px 会顶到
1280 画面两边，一屏只塞得下 4 行 —— 「整行变灰」和「当前行逐字变灰」在图上根本看不出来。

所以拍照时临时改成 **20 字 / 48 px**，拍完立刻写回原值（放在 `finally` 里，不留手尾）。
选 20 字不是随便挑的：正文「跟随范围」的例子、面板上的 `8 行 · 160 字` 全按每行 20 字算，
**图里的参数必须和正文的数字是同一套**，否则读者拿图去对文字，一眼就发现对不上。

### 23.2 ⛔ 两套灰标记，不能混用

| 想数什么 | 加在哪 | 判断方法 |
|---|---|---|
| 整行已念过 | `.line.read` | `el.classList.contains('read')` |
| 当前行念到第几个字 | 当前行的 `.ch.read` | `el.querySelectorAll('.ch.read').length` |

`paint()` 里整行灰只加在 `.line` 上，逐字灰只加在**当前行**的 `.ch` 上。
第一版脚本用 `read == total` 去判「整行灰」，**永远数出 0 行** ——
因为整行灰那一行里，每个 `.ch` 上根本没有 `read` 类。

### 23.3 ⛔ 别抢帧：冻结 + 快门总是差两拍

第一版做法是「跑到命中 → PUT `cps=0.2` 冻住 → 等 350 ms → 按快门」。
拍出来总是比采样**晚两三行**：`Motion` 是带时间常数的平滑跟随（`tau_fwd=0.09`），
`pos` 冻住了它还得追一段；而截图自己也要一两百毫秒。

⚠️ 这比"拍糊了"更难发现：**拍到的是一帧实际没出现过的状态**。
采样说「3 整行灰 + 当前行 5/20」，图上却是「4 整行灰 + 当前行 0/20」。

正解是**两段速度**，让目标状态自己持续足够久：

1. `cps=14` 快跑，几秒就攒够「3 整行灰」
2. 降到 `cps=1.2`（一个字 0.83 秒），等当前行念到 `6 ~ n-6` 字时按快门

1.2 字/秒下，快门延迟两百毫秒只差半个字，拍出来的就是采样那一帧。
**拍完再采一次 DOM 复核**，两次一致才算过：实测 4 行灰 + 当前行 6/20，拍前拍后完全一致 ✅

### 23.4 视口尺寸按内容算，不是一律 1280×720

- 控制台右边栏 `scrollHeight = 901 px`，820 高会把最下面的「开启麦克风 / 自检」切掉 → 用 **960**
- 设置页先量 `documentElement.scrollHeight`（实测 1249），再设成 `max(900, min(h+8, 1600))`
- 提词窗用 **1280×720** —— 16:9 是它的真实形状，别为了"多显示几行"改比例

### 23.5 「跟读中」那张是真跑出来的

自动滚动模式（`follow_mode=auto`）不要麦克风也不要模型，按 `cps` 匀速推进，
所以这一帧完全能让程序自己跑出来，**不需要伪造 `pos`**。
（`applyPos()` 在 IIFE 闭包里拿不到，真要伪造就得劫持 WebSocket —— 有真路径就别走那条。）

### 23.6 中英两份 README 的同步纪律

仓库里现在有两份，**不是"英文版翻译一下发出去"就完了**，它们会一起烂：

| 文件 | 语言 | 地位 |
|---|---|---|
| `README.md` | 中文 | 主版本 —— GitHub 首页默认渲染的就是它 |
| `README.en.md` | 英文 | 对外版本，标题用仓库名 `ai-follow-teleprompter`（不是意译名） |

四条规矩：

- **结构必须一一对应**：小节顺序、标题层级、表格行列全一样。快速自检 —— 两份的**二级 + 三级
  标题总数**应当相等（现在各 **37** 个，连 H1 算是 41）、代码围栏数也应当相等（各 **20** 处）。
  数不上就是漏了一节或多了半节
- **数字只在一处"决定"**：先改中文，再照抄英文。校验办法是数出现次数（如 `2.6 GB`
  两份都该是 5 次、`271` 都是 1 次）。两边数字打架时，**以代码和实测为准**，不以任何一份文档为准
- **图只有一套**：`docs/images/` 那四张被两份共用，重拍一次两边自动都新，不用改 Markdown
- **改完跑一遍锚点校验**：目录是手写的，改标题最容易忘。实测两版各 **29** 个页内链接，全部落地

⚠️ **英文版必须写明「界面是中文」**。英文读者打开程序看到的是中文 UI，如果 README 不交代，
他会照着 "Follow range" 去界面上找，找不到 —— 所以英文版开头就声明，并把要点的控件写成
`中文 (English)` 对照。

---

## 已知局限

- 延迟数字来自公开资料与本机推算，**未实测**；R2 才有真实值。
- 语料库尚未建立，R8 指标目前是目标值，不是承诺值。
- 口音适配未验证，可能需 R4 额外调词典。
- 编辑器为纯文本，不支持图片、表格、角色分色。
- 字号上限受屏宽约束，1080p 约 127 px，再大直接封顶。
- 硬切行可能切断英文单词；口播稿可接受。
- 录制中改字号/改稿需先按 Esc（刻意的设计约束，不是缺陷）。
- 8 轮是净工作轮次，不含你验证与沟通的等待时间。
- **渐隐效果依赖不透明纯色背景**（§4.8）；将来做半透明背景要换 `mask-image`。
- **准备态没有"预览滚动"，空格即可起跑**，模拟推进速度用"速度"滑块（1.0–10.0 字/秒）代替真实语音。
- **改稿后位置回到第 1 字**（D-10），排练到一半改稿会丢位置。
- **服务必须由 `start.bat` 常驻**：我在会话里临时起的那份，会话结束后会被回收，不代表程序有问题。
- **`data/` 目录是唯一持久化**：换电脑/重装要一起拷走 `data/scripts/` 与 `data/state.json`。
- **位置更新约 2–3 Hz（CUDA）/ 约 0.7 Hz（CPU）**：一行 14 字要念 3 秒，够用；但字级变灰是"跳着"走的。CPU 机器跟读会显慢半拍，建议装 CUDA 版 torch。
- **「跟随范围」以外一律不跟**（默认前后各 8 行）：范围外的匹配连候选都进不了，
  屏幕就停在原地。要跳过去请拨滚轮 —— 拨完即重新锚定，比任何算法都快。
  控制台会显示「超出跟随范围 · 差 N 行」，不会静默卡住。
- **范围内的跳读是一步到位的**，没有缓动。这是刻意的：用户要的是"不跟"，
  不是"慢慢跟"—— 慢慢跟意味着它终究会过去，只是让人看得更难受。
- **范围设到 1～2 行时会误伤**：ASR 漏几拍（咳嗽、走音）就超范围了。默认 8 行是有原因的。
- **数据占用面板的「程序本体」不含 `data/` 与 `models/`**：它们各自单独成行，
  否则同一份体积会被算两遍。
- **首次开麦要等 10–20 秒**（导入 torch + 加载权重 + CUDA 预热）。现在这段时间**先开麦录音**，加载完第一拍能吃到最近 4 秒，不至于白念；再往后开关麦只要 1–2 秒（模型已在内存）。
- **删除稿件不可撤销**，没有回收站；录完想留着就导入备份。

---

> 本规划由软件工坊 AI 协作生成，关键决策请由工程负责人复核。
> 版本线：v1.6 = R2 起飞版｜v1.7 = R3 对齐器｜v1.8 = 推进方式开关｜v1.9 = AI 跟随修复 + 稿件删除｜
> v2.0 = 设置页 + 模型自动发现｜**v2.0.1 = 启动器修复（纯 ASCII bat + 依赖自检移入 run.py）**｜
> v2.2 = 进度窗口搬出 Inno + 增量安装 + 暂停/继续｜v2.2.1 = 快捷方式启动修复（pythonw 的 sys.stdout 是 None）｜
> v2.2.3 = 控制台「退出程序」｜v2.2.4 = 安装时程序开着只提示一次，不再逐文件报错｜
> v2.2.4 补 = 源码版快捷方式改指 pythonw（不再弹黑框）+ `win_shortcut.py` 去掉 pywin32 依赖｜
> v2.3.0 = 跟读跳跃收敛（§21）+ 磁盘卫生（§22）｜
> **v2.4.0 = 跟读限位重做：限「范围」不限「速度」（§21，重做四遍）+ 静态资源不再被缓存（§21.9）（当前）**
>
> **2026-11-20 起的新范围另开文件：[`AI提词器-开发规划-v2.3.md`](AI提词器-开发规划-v2.3.md)**。
> v2.3.0 的需求 B/C 已经做完并**回流到本文件的 §21/§22**（那边不再保留"已完成"段落，
> 否则两份文档迟早互相矛盾）；v2.3 文件里剩下的只有**需求 A：独立窗口**。
> 2.4.0 这个号最后由 B（范围限位重做）用掉，A 顺延到 **2.5.0** —— 理由见那份文档的发布节奏表。
> 范围再变就另开文件，不在本文件上打补丁——避免"一处是旧结论、一处是新结论"。

