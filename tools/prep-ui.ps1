# AI 提词器 · 准备运行环境（独立进度窗口）
#
# 为什么要有这个窗口
# ==================
# 上一版把 2.6 GB 的下载放在 Inno 的 [Code] 里用 while 循环轮询。
# 用户的实测结果是：**整个窗口死了**——取消按钮点不动，右上角的最小化和
# 关闭也没反应，只能用任务管理器强杀。
#
# 原因不是 bug，是 Inno 的机制：Pascal Script 跑起来的时候，Inno 不派发
# 输入消息（WM_LBUTTONDOWN / WM_NCLBUTTONDOWN 都不进队列），只有我们自己
# 调 Update 才会重绘。所以界面「看起来在动」（我们强制刷了标签），
# 但任何点击都不会被处理 —— 连标题栏的 X 都不行。
#
# 结论：**长任务不能放在 Inno 的窗口里**。这里把活搬到独立进程：
#   Inno 把向导藏起来 → 启动本脚本（它有真正的消息循环）→ 等它退出 → 收结果
# 用户看到的唯一窗口就是下面这个，最小化、关闭、暂停、取消全都真的能用。
#
# 退出码约定（Inno 只看这个）
# ==========================
#   0 = 全部就绪        3 = 用户取消        4 = 失败        其它 = 失败
# 详细状态另写一份 ASCII 的 prep-result.txt，因为 Inno 读中文文件会乱码。
#
# 增量安装
# ========
# 不闭着眼睛重装。先跑 tools\check_env.py 问三件事：torch 是什么版本、
# 必需包装齐没有、模型在不在。已经满足的步骤**整段跳过**，
# 所以「上次装到一半」再跑一次，只会补没完成的那部分。

param(
  [Parameter(Mandatory = $true)][string]$AppDir,
  [ValidateSet('cuda', 'cpu')][string]$Torch = 'cuda',
  [int]$Model = 1,
  [string]$StatusFile = '',
  [string]$LogFile = '',
  [string]$TmpDir = '',
  [string]$CancelFile = '',
  [string]$PauseFile = '',
  [string]$ResultFile = '',
  # 自测用：指定一个脚本代替 check_env.py，跑完立刻报「已就绪」。
  # 发布版不用，留着是为了能在不下 2.6 GB 的前提下验证界面。
  [string]$FakeStage = '',
  # 自测用：把所有「干活」的阶段都换成这个脚本（不真的下载），
  # 用来验证暂停 / 取消 / 关窗这些交互。
  [string]$FakeWork = '',
  # 自测用：取消时不弹确认框，便于自动化点击。
  [switch]$NoConfirm
)

$ErrorActionPreference = 'Stop'
# 这两个程序集必须先加载，否则 [System.Windows.Forms.Application] 这类
# 类型名在解析时就报「找不到类型」—— 报错还指在下面很远的行上
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles() | Out-Null

# Inno 是用 SW_HIDE 启动我们的：Windows 会把第一次 ShowWindow 的参数忽略掉，
# 改用启动信息里的 SW_HIDE —— 表现就是「脚本跑了，窗口不出现」。
# 所以显式再 Show 一次，并抢到前台，否则用户会以为安装器卡住了。
Add-Type -Namespace AITP -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
'@

# ------------------------------------------------------------------ 路径
$AppDir = (Resolve-Path -LiteralPath $AppDir).Path
if (-not $TmpDir)     { $TmpDir     = Join-Path $AppDir '_tmp' }
if (-not $StatusFile) { $StatusFile = Join-Path $TmpDir 'progress.txt' }
if (-not $CancelFile) { $CancelFile = Join-Path $TmpDir 'cancel.flag' }
if (-not $PauseFile)  { $PauseFile  = Join-Path $TmpDir 'pause.flag' }
if (-not $ResultFile) { $ResultFile = Join-Path $TmpDir 'prep-result.txt' }
if (-not $LogFile)    { $LogFile    = Join-Path $AppDir 'install.log' }

$PythonExe = Join-Path $AppDir 'python\python.exe'
$ToolDir   = Join-Path $AppDir 'tools'

New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

# 子进程（python）的输出按 UTF-8 编码，免得中文路径在 JSON 里变成乱码
$env:PYTHONIOENCODING = 'utf-8'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

# 每次开跑先把上一轮的暗号清掉 —— 不清的话助手一启动就以为用户要取消
Remove-Item -LiteralPath $CancelFile -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $PauseFile  -ErrorAction SilentlyContinue

# ------------------------------------------------------------------ 常量
$TORCH_VERSION = '2.14.0'
$TORCH_INDEX   = 'https://download.pytorch.org/whl/cu126'
$PYPI_MIRROR   = 'https://mirrors.ustc.edu.cn/pypi/simple'
$PYPI_OFFICIAL = 'https://pypi.org/simple'

# ------------------------------------------------------------------ 状态
$script:stages      = @()      # 待执行的阶段（env-check 之后才确定）
$script:idx         = 0
$script:proc        = $null    # 当前子进程
$script:state       = 'init'   # init|running|pausing|paused|cancelling|done|failed
$script:cancelAt    = $null    # 取消后等多久强杀
$script:closeAfter  = $false   # 结束后要不要自己关窗
$script:skipped     = @()      # 跳过了哪些步骤（显示给用户看）
$script:failText    = ''
$script:lastPct     = 0
$script:lastText    = ''
$script:pauseHint   = $false
$script:curStage    = ''       # 当前阶段名，写结果文件时用
$script:retriedRest = $false   # 镜像失败只改走官方源重试一次

# ------------------------------------------------------------------ 界面
$form = New-Object System.Windows.Forms.Form
$form.Text            = 'AI 提词器 · 准备运行环境'
$form.ClientSize      = New-Object System.Drawing.Size(620, 340)
$form.FormBorderStyle = 'FixedSingle'      # 可最小化，不可拉伸
$form.MaximizeBox     = $false
$form.MinimizeBox     = $true
$form.StartPosition   = 'CenterScreen'
$form.BackColor       = [System.Drawing.Color]::White
$form.Font            = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)

# 用程序自己的图标，避免任务栏里是个白板
try {
  $ico = Join-Path $AppDir 'assets\teleprompter.ico'
  if (Test-Path -LiteralPath $ico) {
    $form.Icon = New-Object System.Drawing.Icon($ico)
  }
} catch { }

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Text     = '正在准备运行环境'
$lblTitle.Font     = New-Object System.Drawing.Font('Microsoft YaHei UI', 14, [System.Drawing.FontStyle]::Bold)
$lblTitle.ForeColor = [System.Drawing.Color]::FromArgb(28, 28, 30)
$lblTitle.Location = New-Object System.Drawing.Point(24, 22)
$lblTitle.AutoSize = $true
$form.Controls.Add($lblTitle)

$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Text     = '正在检查这台机器上已有的环境…'
$lblStatus.Font     = New-Object System.Drawing.Font('Microsoft YaHei UI', 10)
$lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(40, 40, 42)
$lblStatus.Location = New-Object System.Drawing.Point(24, 68)
$lblStatus.Size     = New-Object System.Drawing.Size(572, 26)
$lblStatus.AutoEllipsis = $true
$form.Controls.Add($lblStatus)

$lblDetail = New-Object System.Windows.Forms.Label
$lblDetail.Text     = ''
$lblDetail.Font     = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$lblDetail.ForeColor = [System.Drawing.Color]::FromArgb(110, 110, 115)
$lblDetail.Location = New-Object System.Drawing.Point(24, 96)
$lblDetail.Size     = New-Object System.Drawing.Size(572, 22)
$lblDetail.AutoEllipsis = $true
$form.Controls.Add($lblDetail)

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Location = New-Object System.Drawing.Point(24, 126)
$bar.Size     = New-Object System.Drawing.Size(572, 16)
$bar.Minimum  = 0
$bar.Maximum  = 100
$bar.Value    = 0
$form.Controls.Add($bar)

$lblSkip = New-Object System.Windows.Forms.Label
$lblSkip.Text     = ''
$lblSkip.Font     = New-Object System.Drawing.Font('Microsoft YaHei UI', 8.5)
$lblSkip.ForeColor = [System.Drawing.Color]::FromArgb(120, 120, 126)
$lblSkip.Location = New-Object System.Drawing.Point(24, 160)
$lblSkip.Size     = New-Object System.Drawing.Size(572, 96)
$form.Controls.Add($lblSkip)

$lnkLog = New-Object System.Windows.Forms.LinkLabel
$lnkLog.Text     = '查看安装日志'
$lnkLog.Location = New-Object System.Drawing.Point(24, 300)
$lnkLog.AutoSize = $true
$lnkLog.LinkColor = [System.Drawing.Color]::FromArgb(0, 102, 204)
$form.Controls.Add($lnkLog)

$btnPause = New-Object System.Windows.Forms.Button
$btnPause.Text     = '暂停'
$btnPause.Location = New-Object System.Drawing.Point(376, 292)
$btnPause.Size     = New-Object System.Drawing.Size(112, 32)
$btnPause.FlatStyle = 'System'
$form.Controls.Add($btnPause)

$btnCancel = New-Object System.Windows.Forms.Button
$btnCancel.Text     = '取消'
$btnCancel.Location = New-Object System.Drawing.Point(496, 292)
$btnCancel.Size     = New-Object System.Drawing.Size(100, 32)
$btnCancel.FlatStyle = 'System'
$form.Controls.Add($btnCancel)

# ------------------------------------------------------------------ 小工具
function Write-Result([string]$state, [string]$stage, [int]$code) {
  # 纯 ASCII，Inno 那边按 GBK/ANSI 读都不会坏
  $lines = @("state=$state", "stage=$stage", "code=$code")
  try {
    Set-Content -LiteralPath $ResultFile -Value $lines -Encoding ASCII -Force
  } catch { }
}

function Add-Log([string]$msg) {
  try {
    Add-Content -LiteralPath $LogFile -Value ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg) -Encoding UTF8
  } catch { }
}

function Quote-Arg([string]$s) {
  # Start-Process 的 ArgumentList 数组是「用空格拼起来」，不会自动加引号，
  # 所以路径里有空格时必须自己包 —— 用户完全可能装在 C:\Program Files 下
  if ($s -match '[\s"]') { return '"' + ($s -replace '"', '\"') + '"' }
  return $s
}

function Start-Child([string]$exe, [string[]]$argv, [string]$stdout) {
  # 为什么用 .NET 的 ProcessStartInfo 而不是 Start-Process：
  #   · Start-Process 的 -ArgumentList 数组是「用空格拼起来」，不会自动加引号，
  #     路径里有空格（C:\Program Files\...）会散架 —— 这里自己 Quote-Arg
  #   · CreateNoWindow 比 -WindowStyle Hidden 更干净：子进程根本不建控制台
  #   · 拿到的是 .NET 的 Process 对象，HasExited / ExitCode / 输出流都直接可用
  $argLine = ($argv | ForEach-Object { Quote-Arg $_ }) -join ' '

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName               = $exe
  $psi.Arguments              = $argLine
  $psi.WorkingDirectory       = $AppDir
  $psi.UseShellExecute        = $false
  $psi.CreateNoWindow         = $true
  $psi.WindowStyle            = [System.Diagnostics.ProcessWindowStyle]::Hidden
  if ($stdout) { $psi.RedirectStandardOutput = $true }

  $p = New-Object System.Diagnostics.Process
  $p.StartInfo = $psi
  [void]$p.Start()
  return $p
}

# ------------------------------------------------------------------ 阶段定义
function New-Stage {
  param(
    [string]$Name, [string]$Label, [string]$Exe,
    [string[]]$Argv, [int]$Lo, [int]$Hi, [string]$Out = ''
  )
  return [pscustomobject]@{
    Name = $Name; Label = $Label; Exe = $Exe; Argv = $Argv
    Lo = $Lo; Hi = $Hi; Out = $Out
  }
}

function New-Helper-Stage {
  param([string]$Name, [string]$Label, [string]$Mode, [string[]]$Extra, [int]$Lo, [int]$Hi)

  $argv = @(
    (Join-Path $ToolDir 'pip_progress.py')
    '--mode', $Mode
    '--status', $StatusFile
    '--log', $LogFile
    '--tmp', $TmpDir
    '--label', $Label
    '--cancel', $CancelFile
    '--pause', $PauseFile
    '--lo', "$Lo", '--hi', "$Hi"
  ) + $Extra

  return New-Stage -Name $Name -Label $Label -Exe $PythonExe -Argv $argv -Lo $Lo -Hi $Hi
}

function Get-Torch-Stage {
  if ($Torch -eq 'cpu') {
    # CPU 版走普通 pip：240 MB，没必要自己抓 wheel
    return New-Helper-Stage -Name 'torch' -Mode 'pip' -Lo 0 -Hi 55 `
      -Label '正在下载 PyTorch CPU 版（约 240 MB）' `
      -Extra @('--', '--cache-dir', (Join-Path $TmpDir 'pipcache'),
               "torch==$TORCH_VERSION", '--index-url', $PYPI_MIRROR)
  }
  return New-Helper-Stage -Name 'torch' -Mode 'torch' -Lo 0 -Hi 55 `
    -Label '正在下载 PyTorch 显卡加速版（约 2.6 GB）' `
    -Extra @('--version', $TORCH_VERSION, '--index', $TORCH_INDEX, '--py-tag', 'cp313')
}

function Get-Rest-Stage([string]$indexUrl) {
  $extra = @('--', '--cache-dir', (Join-Path $TmpDir 'pipcache'),
             '-r', (Join-Path $AppDir 'requirements.txt'))
  if ($indexUrl) { $extra += @('--index-url', $indexUrl) }
  return New-Helper-Stage -Name 'rest' -Mode 'pip' -Lo 55 -Hi 85 `
    -Label '正在安装语音识别依赖（transformers / qwen-asr 等）' -Extra $extra
}

function Get-Model-Stage {
  $argv = @(
    (Join-Path $ToolDir 'download_model.py')
    '--status', $StatusFile
    '--cancel', $CancelFile
    '--pause', $PauseFile
    '--lo', '85', '--hi', '100'
    '--label', '正在下载语音识别模型（1.8 GB）'
  )
  return New-Stage -Name 'model' -Label '正在下载语音识别模型（1.8 GB）' `
                   -Exe $PythonExe -Argv $argv -Lo 85 -Hi 100
}

function Get-Check-Stage([string]$name, [string]$out) {
  $argv = @((Join-Path $ToolDir 'check_env.py'), '--json')
  if ($FakeStage) { $argv = @($FakeStage) }
  return New-Stage -Name $name -Label '正在检查这台机器上已有的环境…' `
                   -Exe $PythonExe -Argv $argv -Lo 0 -Hi 0 -Out $out
}

function Read-Env([string]$path) {
  try {
    $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    return $raw | ConvertFrom-Json
  } catch {
    Add-Log "读不出体检结果：$_"
    return $null
  }
}

# ------------------------------------------------------------------ 计划
function Build-Plan($env) {
  $script:stages = @()
  $script:skipped = @()

  Add-Log ("体检：torch=[" + $env.torch + "] missing=[" + (@($env.missing) -join ',') +
           "] asr=[" + (@($env.missing_asr) -join ',') + "] model=[" + $env.model + "]")

  if ($env -and $env.torch) {
    $v = [string]$env.torch
    if ($v.StartsWith($TORCH_VERSION)) {
      $mode = '仅 CPU'
      if ($env.torch_cuda) { $mode = 'CUDA 可用' }
      $script:skipped += "PyTorch $v（$mode，不用重下 2.6 GB）"
    } else {
      $script:stages += Get-Torch-Stage
    }
  } else {
    $script:stages += Get-Torch-Stage
  }

  $missReq = @()
  $missAsr = @()
  if ($env) {
    if ($env.missing)     { $missReq = @($env.missing) }
    if ($env.missing_asr) { $missAsr = @($env.missing_asr) }
  }
  if (($missReq.Count + $missAsr.Count) -eq 0) {
    $script:skipped += '语音识别依赖（transformers / qwen-asr 等已就位）'
  } else {
    $script:stages += Get-Rest-Stage $PYPI_MIRROR
  }

  if ($Model -eq 1) {
    if ($env -and $env.model) {
      $script:skipped += ('语音识别模型（' + (Split-Path -Leaf ([string]$env.model)) + ' 已就位）')
    } else {
      $script:stages += Get-Model-Stage
    }
  } else {
    $script:skipped += '语音识别模型（你没勾「现在就下载」）'
  }

  # 最后再体检一次：pip 报成功但 import 不进去，是最难查的一类问题
  $script:stages += Get-Check-Stage 'env-verify' (Join-Path $TmpDir 'env-verify.json')

  if ($FakeWork) {
    # 自测：把「干活」阶段全换成假脚本，一个字节都不下
    $fake = @()
    foreach ($s in $script:stages) {
      if ($s.Name -like 'env-*') { $fake += $s; continue }
      $fake += New-Stage -Name $s.Name -Label $s.Label -Exe $PythonExe `
        -Argv @($FakeWork, $s.Name, "$($s.Lo)", "$($s.Hi)", $StatusFile, $CancelFile, $PauseFile) `
        -Lo $s.Lo -Hi $s.Hi
    }
    $script:stages = $fake
  }

  $script:skipped | ForEach-Object { Add-Log "跳过：$_" }
  Add-Log ("计划：" + ((@($script:stages) | ForEach-Object { $_.Name }) -join ' → '))
}

# ------------------------------------------------------------------ 跑阶段
function Start-Current {
  if ($script:idx -ge $script:stages.Count) { Finish-All; return }

  $st = $script:stages[$script:idx]
  $script:curStage = $st.Name
  $script:state  = 'running'
  $script:lastPct = 0
  $lblStatus.Text = $st.Label
  $lblDetail.Text = ''
  $lblTitle.Text  = '正在准备运行环境'
  if ($st.Lo -eq 0 -and $st.Hi -eq 0) {
    # 体检阶段没有真实百分比，用跑马灯表示「在动」。
    # 一定要把 Value 清零：Marquee 模式下 Value 不参与绘制，但从 Marquee
    # 切回 Continuous 时会沿用旧值 —— 不清就会看到进度条一开始就半满。
    $bar.Value = 0
    $bar.Style = 'Marquee'
    $bar.MarqueeAnimationSpeed = 30
  } else {
    $bar.Style = 'Continuous'
    $bar.Value = [Math]::Max($bar.Value, [Math]::Min(100, $st.Lo))
  }

  Add-Log ("开始阶段 {0}" -f $st.Name)
  try {
    $script:proc = Start-Child -exe $st.Exe -argv $st.Argv -stdout $st.Out
  } catch {
    $script:failText = "启动子进程失败：$_"
    Add-Log $script:failText
    Complete-Run 'failed' 4
  }
}

function Complete-Run([string]$state, [int]$code) {
  $script:state = $state
  Write-Result $state $script:curStage $code
  Add-Log ("结束：{0}（{1}）" -f $state, $code)

  if ($state -eq 'ok') {
    $lblTitle.Text  = '运行环境已就绪'
    $lblStatus.Text = '可以开始使用了。'
    $lblDetail.Text = ''
    $bar.Style = 'Continuous'
    $bar.Value = 100
  } elseif ($state -eq 'cancelled') {
    $lblTitle.Text  = '已停止'
    $lblStatus.Text = '已下载的部分都保留着，下次运行安装程序会接着来。'
  } else {
    $lblTitle.Text  = '没能装完'
    $lblStatus.Text = $script:failText
  }
  $btnPause.Enabled  = $false
  $btnCancel.Enabled = $false
  $script:closeAfter = $true
  $script:closeAt    = (Get-Date).AddSeconds(1)
}

function On-StageExit([System.Diagnostics.Process]$p) {
  $st = $script:stages[$script:idx]
  $code = $p.ExitCode

  # 体检阶段的 stdout 就是 JSON。这里才去读：输出只有几百字节，
  # 等进程退出后一次读完最省事（不会有缓冲区填满的风险）。
  if ($st.Out) {
    try {
      $out = $p.StandardOutput.ReadToEnd()
      Set-Content -LiteralPath $st.Out -Value $out -Encoding UTF8 -NoNewline
    } catch {
      Add-Log "读子进程输出失败：$_"
    }
  }

  Add-Log ("阶段 {0} 退出码 {1}" -f $st.Name, $code)

  if ($code -eq 4) {                      # 用户暂停
    $script:state = 'paused'
    $lblTitle.Text  = '已暂停'
    $lblDetail.Text = '点「继续」接着下，已经下的部分不会重来。'
    $btnPause.Text  = '继续'
    $btnPause.Enabled = $true
    return
  }
  if ($code -eq 3) {                      # 用户取消
    $script:idx = $script:stages.Count
    Complete-Run 'cancelled' 0
    return
  }
  # ⛔ 体检阶段把「1」也算成功。check_env.py 用退出码 1 表示**有缺的包**，
  #    而那正是全新安装的常态（torch 一个都还没装）。它真正的结论在 stdout 的
  #    JSON 里，退出码只是个顺手的人读提示。
  #    不这么写的话，装到一台**干净机器**上必定在第一步就失败 —— 实测 2.3.0 的
  #    第一次全新安装就栽在这儿，而之前每次都覆盖安装（包本来就齐、退出码 0），
  #    所以这个坑一直没暴露。env-verify 不在此列：那时该有的都得有了，必须 0。
  $okCodes = @(0)
  if ($st.Name -eq 'env-check') { $okCodes = @(0, 1) }
  if ($okCodes -notcontains $code) {
    # 镜像偶尔缺新包：这一次退回官方 PyPI 重试。别的阶段不重试 ——
    # pip 自己已经重试过三轮了，再包一层只会让用户多等十分钟。
    if ($st.Name -eq 'rest' -and -not $script:retriedRest) {
      $script:retriedRest = $true
      Add-Log '镜像失败，改走官方 PyPI 重试'
      $lblStatus.Text = '镜像里缺包，改走官方 PyPI 再试…'
      $script:stages[$script:idx] = Get-Rest-Stage $PYPI_OFFICIAL
      Start-Current
      return
    }
    $script:failText = Get-FailText $st.Name $code
    $script:idx = $script:stages.Count
    Complete-Run 'failed' $code
    return
  }

  # 成功：体检类阶段要先读结果再决定下一步
  if ($st.Name -eq 'env-check') {
    $env = Read-Env $st.Out
    if ($null -eq $env) {
      $script:failText = '读不出环境检查结果，安装包里可能缺 tools\check_env.py。'
      Complete-Run 'failed' 4
      return
    }
    Build-Plan $env
    if ($script:skipped.Count -gt 0) {
      $lblSkip.Text = "已跳过：" + ($script:skipped -join "`r`n")
    }
    # 体检阶段本身不在新计划里，索引必须归零重来 ——
    # 写成 ++ 的话第一个真正的阶段会被跳过（实测踩过：torch 直接消失）
    $script:idx = 0
    Start-Current
    return
  }
  if ($st.Name -eq 'env-verify') {
    $env = Read-Env $st.Out
    $missReq = @()
    $missAsr = @()
    if ($env) {
      if ($env.missing)     { $missReq = @($env.missing) }
      if ($env.missing_asr) { $missAsr = @($env.missing_asr) }
    }
    if (($missReq.Count + $missAsr.Count) -gt 0) {
      $script:failText = '装完了但自检没过，缺：' + (($missReq + $missAsr) -join '、')
      Complete-Run 'failed' 5
      return
    }
    $script:idx++
    Complete-Run 'ok' 0
    return
  }

  $script:idx++
  Start-Current
}

function Get-FailText([string]$stage, [int]$code) {
  switch ($stage) {
    'torch'  { return "PyTorch 没装成功（退出码 $code）。多半是网络断了，或磁盘空间不够（CUDA 版装完要 4 GB 出头）。已经下的部分会保留，下次接着下。" }
    'rest'   { return "依赖包没装全（退出码 $code）。已经装好的包不会重装，再跑一次只会补缺的。" }
    'model'  { return "模型没下完（退出码 $code）。不影响打开程序，可以在程序里重新下载。" }
    default  { return "这一步没成功（退出码 $code）。日志在 install.log。" }
  }
}

function Finish-All { Complete-Run 'ok' 0 }

# ------------------------------------------------------------------ 暂停/取消
function Request-Pause {
  if ($script:state -eq 'running' -and $script:proc -ne $null) {
    New-Item -ItemType File -Force -Path $PauseFile | Out-Null
    $script:state = 'pausing'
    $btnPause.Enabled = $false
    $lblTitle.Text = '正在暂停…'
    Add-Log '用户点了暂停'
    return
  }
  if ($script:state -eq 'paused') {
    Remove-Item -LiteralPath $PauseFile -ErrorAction SilentlyContinue
    $btnPause.Text = '暂停'
    Add-Log '用户点了继续'
    Start-Current
  }
}

function Request-Cancel {
  if ($script:state -in @('done', 'failed', 'cancelled')) { return }
  if ($script:state -eq 'cancelling') { return }

  $r = [System.Windows.Forms.DialogResult]::Yes
  if (-not $NoConfirm) {
    $r = [System.Windows.Forms.MessageBox]::Show(
      "确定要停止安装吗？`r`n`r`n已经下载的部分会保留，下次运行安装程序接着下，不会从头来。",
      '停止安装',
      [System.Windows.Forms.MessageBoxButtons]::YesNo,
      [System.Windows.Forms.MessageBoxIcon]::Question,
      [System.Windows.Forms.MessageBoxDefaultButton]::Button2)
  }
  if ($r -ne [System.Windows.Forms.DialogResult]::Yes) { return }

  New-Item -ItemType File -Force -Path $CancelFile | Out-Null
  $script:state = 'cancelling'
  $script:cancelAt = (Get-Date).AddSeconds(8)
  $lblTitle.Text  = '正在停止…'
  $lblDetail.Text = '正在让下载助手收手，最多等 8 秒。'
  $btnPause.Enabled  = $false
  $btnCancel.Enabled = $false
  Add-Log '用户点了取消'
}

$btnPause.Add_Click({ Request-Pause })
$btnCancel.Add_Click({ Request-Cancel })
$lnkLog.Add_LinkClicked({
  try { Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $LogFile + '"') } catch { }
})

# 点右上角的 X = 取消。不能让它「悄悄关掉、下载还在后台跑」
$form.Add_FormClosing({
  param($sender, $e)
  if ($script:state -in @('running', 'pausing', 'paused')) {
    $e.Cancel = $true
    Request-Cancel
  }
})

# ------------------------------------------------------------------ 心跳
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 200

$timer.Add_Tick({
  # 1. 读状态文件，刷新界面
  if (Test-Path -LiteralPath $StatusFile) {
    try {
      $line = Get-Content -LiteralPath $StatusFile -Raw -Encoding UTF8
      if ($line) {
        $parts = $line.Trim().Split('|')
        if ($parts.Count -ge 3) {
          $stage = $parts[0]
          $pct = 0
          [int]::TryParse($parts[1], [ref]$pct) | Out-Null
          $text = $parts[2]

          if ($stage -eq 'PAUSED') {
            $lblStatus.Text = $text
          } elseif ($stage -eq 'FAIL') {
            $lblStatus.Text = $text
            $lblDetail.Text = ''
          } else {
            if ($script:state -eq 'running' -or $script:state -eq 'pausing') {
              $lblStatus.Text = $text
            }
            if ($pct -gt $script:lastPct) { $script:lastPct = $pct }
            if ($bar.Style -ne 'Marquee') {
              $bar.Value = [Math]::Max($bar.Value, [Math]::Min(100, $script:lastPct))
            }
            # 解压安装阶段不能暂停：pip 正在写 site-packages，掐了会留下半个包
            $canPause = ($stage -eq 'DOWNLOAD' -or $stage -eq 'LOOKUP')
            if ($script:state -eq 'running') {
              if ($btnPause.Enabled -ne $canPause) { $btnPause.Enabled = $canPause }
              if ($canPause -ne $script:pauseHint) {
                $script:pauseHint = $canPause
                if ($canPause) { $lblDetail.Text = '' }
                else { $lblDetail.Text = '解压安装中不能暂停，再等一会儿。' }
              }
            }
          }
        }
      }
    } catch { }
  }

  # 2. 子进程退出了没有
  if ($script:proc -ne $null) {
    if ($script:proc.HasExited) {
      $p = $script:proc
      $script:proc = $null
      On-StageExit $p
    } elseif ($script:state -eq 'cancelling' -and $script:cancelAt -ne $null -and (Get-Date) -gt $script:cancelAt) {
      # 8 秒还不走，说明它卡在某个不查暗号的调用里（例如 pip 正在解压）。
      # 这时候只能连子进程树一起干掉 —— 至少比让用户开任务管理器强。
      Add-Log '助手没在 8 秒内收手，强制结束'
      try { & taskkill.exe /T /F /PID $script:proc.Id | Out-Null } catch { }
      $script:cancelAt = (Get-Date).AddSeconds(4)
    }
  }

  # 3. 该不该自己关窗
  if ($script:closeAfter -and $script:closeAt -and (Get-Date) -gt $script:closeAt) {
    $script:closeAfter = $false
    $timer.Stop()
    $form.Close()
  }
})

$form.Add_Shown({
  try {
    [void][AITP.Native]::ShowWindow($form.Handle, 5)     # SW_SHOW
    [void][AITP.Native]::SetForegroundWindow($form.Handle)
  } catch { }
  $timer.Start()
  $lblSkip.Text = ''
  # 第一步永远是体检：它决定后面哪些步骤可以直接跳过
  $script:stages = @(Get-Check-Stage 'env-check' (Join-Path $TmpDir 'env-check.json'))
  $script:idx = 0
  Start-Current
})

[void]$form.ShowDialog()

# 窗口关了但子进程还活着 —— 别把它留成孤儿
if ($script:proc -ne $null -and -not $script:proc.HasExited) {
  try { & taskkill.exe /T /F /PID $script:proc.Id | Out-Null } catch { }
}

switch ($script:state) {
  'ok'        { exit 0 }
  'cancelled' { exit 3 }
  default     { exit 4 }
}
