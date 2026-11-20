# AI 提词器 · 开发规划 v2.3

**需求 A：提词窗脱离浏览器，成为独立窗口**

> 承接 [`AI提词器-开发规划-v2.0.md`](AI提词器-开发规划-v2.0.md)。
> v2.0 那份的结尾写明了「范围再变就另开文件，不在原文件上打补丁 —— 避免一处是旧结论、
> 一处是新结论」，所以新范围单独开一份。
>
> **本文档只写「还没做的东西」。** 做完的结论回流到 v2.0 对应章节，这里不保留 ——
> 否则两份文档迟早互相矛盾。

| | |
|---|---|
| 基线 | **v2.3.0 已发布**：跳跃收敛（→ v2.0 §21）、磁盘卫生（→ v2.0 §22） |
| 本文档剩下的 | **只有需求 A**，目标版本 2.4.0 |
| 日期 | 2026-11-20 立项｜2026-11-21 更新（B/C 已完成并回流） |

---

## 目录

- [需求 A：提词窗脱离浏览器，成为独立窗口](#需求-a提词窗脱离浏览器成为独立窗口)
- [发布节奏](#发布节奏)
- [验收底线](#验收底线)

---

## 需求 A：提词窗脱离浏览器，成为独立窗口

### A.1 现在是什么样

控制台里点「打开提词窗」，走的是 `web/console.js` 里的：

```js
window.open('/prompter', 'prompter', 'width=1280,height=720');
```

就是一个**浏览器弹出窗口**。实际遇到的别扭：

- 窗口上沿有浏览器残留（看具体浏览器，有的还有标签栏/书签栏）
- 受浏览器缩放、快捷键、焦点策略影响 —— Ctrl+滚轮一下就改了整页比例
- 拖到第二块屏、全屏、置顶，全看浏览器心情
- F11 是**页面全屏**（浏览器自己的全屏），不是窗口全屏，退出路径也不一致
- 任务栏里它跟浏览器是一体的，切窗口时容易和"浏览器"混起来

**好消息**：提词窗的内容是纯前端（`web/prompter.*`），和后端只通过 WebSocket 通信。
换壳**不需要动后端任何逻辑** —— 这是这个需求能低成本做完的前提。

### A.2 三条备选路线

| | 做法 | 新增依赖 | 算不算独立窗口 | 工作量 | 风险 |
|---|---|---|---|---|---|
| **A1** Edge/Chrome `--app=` | 调 `msedge.exe --app=<url> --window-size=1280,720` | **无** | 半（无地址栏/标签栏，独立任务栏条目，但仍是浏览器进程） | 约半天 | 机器上得有 Edge 或 Chrome |
| **A2** pywebview + WebView2 | 用 WebView2 建真正的原生窗口 | `pywebview` + **系统要有 WebView2 运行时** | 是 | 2–3 天 | Win10 默认没有 WebView2；事件循环与 uvicorn 冲突 |
| **A3** Electron / Tauri | 打包一整个 Chromium | 100 MB+ | 是 | 1 周+ | 直接推翻「安装包 13 MB」这条取舍 |

### A.3 ⛔ 为什么暂时不选 A2

本机实测（也就是大多数用户的环境）：

```
系统      Windows 10.0.19045（Win10 22H2）
Edge      157.0.4341.60            ← 有
WebView2  C:\Program Files (x86)\Microsoft\EdgeWebView\Application\   ← 空
          %LOCALAPPDATA%\Microsoft\EdgeWebView\Application\           ← 也空
```

**Win11 自带 WebView2，Win10 不带。** 选 A2 就等于给 Win10 用户加一道前置安装：
要么装 Evergreen 引导器（约 2 MB，但要联网、要用户点同意），要么把固定版运行时
（约 130 MB）塞进安装包 —— 后者直接和「安装包越小越好」打架。

为了一个"窗口边框"付这个代价不划算。**先做 A1，A2 留作后续可选升级**
（真到那天，也是"检测到 WebView2 就用，没有就退回 A1"）。

### A.4 A1 的实现路径

**第 1 步 · 找浏览器**（新增 `app/win_window.py`）

按顺序找，找到第一个就用：
1. `%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe`
2. `%ProgramFiles%\Microsoft\Edge\Application\msedge.exe`
3. `%ProgramFiles%\Google\Chrome\Application\chrome.exe`
4. `%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe`
5. 注册表 `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe`

找不到就退回 `webbrowser.open(url)` —— **不能因为找不到浏览器就打不开程序**。

**第 2 步 · 起窗口**

```python
subprocess.Popen([
    exe,
    f"--app={url}",
    f"--window-size={w},{h}",
    "--disable-features=Translate,msEdgeSidebarV2",   # 别在本地应用里弹翻译/侧栏
], creationflags=0x08000000)   # CREATE_NO_WINDOW，别闪一个黑框
```

⛔ **不要加 `--user-data-dir`**。加了会生成一个几十 MB 的浏览器 profile 目录
（缓存、GPU 缓存、Service Worker），白白吃掉安装目录体积，又正好撞上刚做完的
磁盘卫生（v2.0 §22）想解决的"越用越胖"。用默认 profile 就行 ——
本地 127.0.0.1 页面不存在隐私或会话问题。

**第 3 步 · 让控制台能触发它**

JS 没法启动进程，所以加一个接口：

```
POST /api/open_prompter   → {"ok": true, "via": "edge-app" | "browser"}
```

`console.js` 里把 `window.open(...)` 换成先调这个接口，**接口失败再退回 `window.open`**
（比如后端被防火墙挡了、或者用户在别的机器上开）。

**第 4 步 · 控制台自己也用 app 模式**

`run.py` 里 `_open(url)` 现在走 `webbrowser.open`，改成同一套逻辑：
开机时控制台也以 app 窗口打开。这样"脱离浏览器"是**整体成立**的，
而不是只有提词窗特殊。

> 保留一个开关：`ui["app_window"]`（默认 `true`）。有人就是想用浏览器 + 扩展
> （比如录屏插件），得让他能退回去。设置页放一个勾选框。
>
> ⚠️ 这个键要加进 `config.DEFAULT_UI`。按 v2.0 §22 的规矩，读取一律用
> `ui.get("app_window", True)`，别用 `ui["app_window"]`。

### A.5 这一步刻意不做的

- **不做无边框 + 自绘标题栏**。Edge app 窗口自带一条细标题栏，反而好拖拽、好关。
- **不做置顶（always on top）**。Edge 命令行没有可靠的置顶参数；要做就得走 Win32
  `SetWindowPos(HWND_TOPMOST)`，得先按标题/进程找到那个窗口 —— 留到 A2 再做。
- **不做多窗口管理**。程序本来就只需要"一个控制台 + 一个提词窗"。

### A.6 验收

- 点「打开提词窗」→ 出来一个**没有地址栏、没有标签栏**的窗口，任务栏有独立条目和图标
- 窗口能拖到第二块屏、能 F11 全屏、空格/Esc/滚轮照常
- 关掉提词窗，服务和录音状态不受影响
- 把 `ui["app_window"]` 关掉 → 回到浏览器窗口，功能一样
- 找 Edge 路径失败时（临时改名目录模拟）→ 自动退回 `webbrowser.open`，不报错
- `python tests/run_all.py --fast` 全过（v2.3.0 的基线是 **249 项 / 6 个文件**）
- **装完之后 `data/` 不许出现新的目录** —— 这是 A × C 的交叉检查项：
  一旦有人给 Edge 加了 `--user-data-dir`，安装目录会凭空多出几十 MB

---

## 发布节奏

| 顺序 | 需求 | 版本 | 状态 |
|---|---|---|---|
| 1 | C 磁盘卫生 | 2.3.0 | ✅ 已发布（v2.0 §22） |
| 2 | B 跳跃限制 | 2.3.0 | ✅ 已发布（v2.0 §21） |
| 3 | **A 独立窗口** | **2.4.0** | ⬜ 未开始 |

**为什么 A 必须单独走一版**：它改的是"程序怎么被启动"，出问题会直接表现为"点不开"。
和 B/C 混在一个版本里，回滚时会把两个已经验证好的功能一起退掉。

### 最小动作

```bash
python tests/run_all.py --fast        # 249 项基线，新增用例要在这里面
python tools/build_installer.py --version 2.4.0
# 发版流程见 v2.0 §17（含 ⛔ Release 附件名只能用 ASCII，见 §17.7）
```

另加：在【没装 WebView2 的机器】上验一遍（本机就是，正好）。

---

## 验收底线

1. `python tests/run_all.py --fast` **全过**，新增参数要有测试
2. 老 `data/state.json`（没有新区段）读进来不报错 —— `store.py` 的 `dict(DEFAULT_UI)`
   会补默认值，但**新代码必须用 `ui.get("key", 默认值)` 而不是 `ui["key"]`**，
   防止将来哪天有人绕过 `store.py` 直接构造 `ui`
3. 极端环境不崩：**没装 WebView2**、**没有麦克风**、**空稿件**、**只读安装目录**
   —— 这四个是本项目历史上真出过问题的地方
