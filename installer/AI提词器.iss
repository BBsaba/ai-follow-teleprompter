; ============================================================================
;  AI 提词器 —— Windows 安装程序脚本（Inno Setup 6.3+ / 7.x）
;
;  编译：python tools\build_installer.py
;        （它会先准备 ..\build\payload\ 再调 ISCC，别单独编译本文件）
;
;  设计取舍（改之前先看这几条）：
;
;  1. 安装包里【不放】torch / transformers / 模型权重。
;     放进去就是 1 GB 起步，用户下载要等更久，而且他可能根本不用显卡。
;     这里只带 11 MB 的官方 embeddable Python + 2 MB 代码，装的时候按需联网拉。
;
;  2. 不许要管理员权限。装到 %LOCALAPPDATA%\Programs 下，卸载在
;     「设置 → 应用」里能看到，不需要动 Program Files。
;
;  3. 依赖装在 {app}\python\Lib\site-packages 里（不是外部 venv）。
;     好处：整个程序就是一个文件夹，卸载时删目录就干净了，不会在用户机器上
;     留一堆散落的包；也不依赖用户自己装的 Python。
;
;  4. 安装期间的长任务（pip 装 2.6 GB、下 1.8 GB 模型）**不在本文件的窗口里跑**。
;     2026-11-19 实测：Pascal Script 执行期间 Inno 不派发输入消息，所以向导窗口
;     里的「取消」「最小化」「✕」全是死的，只有我们自己 Update 的标签会重绘。
;     现在的分工：
;        本文件              页面 → 复制文件 → 藏起向导 → 等 → 读结果
;        tools\prep-ui.ps1   PowerShell + WinForms 的独立窗口（真正的消息循环），
;                            带暂停 / 取消 / 关闭，进度实时刷新
;        tools\pip_progress.py / download_model.py   真正干活的助手
;        tools\check_env.py  体检，决定哪几步可以整段跳过（增量安装）
;     详细来龙去脉见 docs\AI提词器-开发规划-v2.0.md §18.13。
;     ⛔ 不要退回「在 CurStepChanged 里开循环 + 轮询 CancelButton.Enabled」那一版。
; ============================================================================

#define MyAppName        "AI 提词器"
#define MyAppNameEn      "AITeleprompter"
#define MyAppPublisher   "公功供工"
#define MyAppURL         "https://github.com/BBsaba/ai-follow-teleprompter"
#define MyAppExeName     "run.py"
#define PayloadDir       "..\build\payload"

; 版本号由 build_installer.py 用 /DMyAppVersion= 传进来
#ifndef MyAppVersion
  #define MyAppVersion "2.1.1"
#endif

; CUDA 版 torch 的索引地址。改这里就是改「装哪个显卡驱动对应的 torch」。
; cu126 是实测能在这台机器（RTX 3060 Ti / 驱动 5xx）上跑的那一版。
#define TorchVersion     "2.14.0"
#define TorchCudaIndex   "https://download.pytorch.org/whl/cu126"
; 国内镜像：非 torch 的包走这里，实测 99 MB/s（清华源在某些网络下会 403）
#define PypiMirror       "https://mirrors.ustc.edu.cn/pypi/simple"


[Setup]
; AppId 是卸载与升级的唯一身份，一旦发版就不要再改
AppId={{7E4C1A62-9B3D-4F58-8A21-5D6C0E9B4A73}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright=Copyright (C) 2026 {#MyAppPublisher} · AGPL-3.0

DefaultDirName={autopf}\{#MyAppNameEn}
; ⛔ 必须写 no。默认值是 auto —— 一旦检测到「同 AppId 的旧版本已安装」，
;    Inno 会把这页整个藏掉，用户看到的流程里就没有选目录这一步了
;    （实测：第一次装能看到「选择安装位置」，升级装 2.1.2 时凭空消失）。
;    用户明确要求「装哪个盘我自己定」，所以强制常显。
DisableDirPage=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=AI提词器-{#MyAppVersion}-安装程序
SetupIconFile=..\assets\teleprompter.ico
UninstallDisplayIcon={app}\assets\teleprompter.ico
UninstallDisplayName={#MyAppName}

; 不需要管理员：装到 {autopf} 在 lowest 下会解析成
; %LOCALAPPDATA%\Programs，用户自己就能装、自己就能卸
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
DisableWelcomePage=no
CloseApplications=no
RestartApplications=no
; 安装要联网，没网就别让用户白等
SetupLogging=yes
; 防止「双击两下」开出两个安装器。用户被上一版冻住过，很容易以为自己没点中
; 又点一次 —— 实测那次同时跑了两份，抢同一个进度文件和同一个下载缓存。
SetupMutex=AITeleprompterSetupMutex
; ⛔ 提词器开着的时候不能装：pythonw.exe 已经把 python313.dll / libcrypto-3.dll
;    这些映射进内存，Windows 不允许删除被映射的文件，Inno 的 DeleteFile 会报
;    「错误代码 5 拒绝访问」，而且是**每个被锁文件弹一次**——
;    实测用户遇到的是几十个「重试 / 跳过此文件」排着队，只能一个个点跳过。
;    程序启动时会 CreateMutex 这个名字（见 run.py 的 _hold_instance_mutex），
;    名字必须一字不差。有它，向导出现之前就只弹一次「请先退出」。
AppMutex=AITeleprompterRunning


[Languages]
Name: "zhcn"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"


; 目录页那行说明：直接告诉他「换目录 = 重新下依赖」，
; 否则用户以为换个盘只是挪文件，白等 2.6 GB 才发现。
[Messages]
zhcn.SelectDirDesc=装到哪个文件夹由你决定。沿用上次的目录会复用已下载的依赖；换到新目录需要重新下载（显卡版约 2.6 GB，仅 CPU 约 240 MB）。

; AppMutex 命中时的那句话。默认文案只说「请关闭程序」，
; 可我们这个是 pythonw，没有窗口，也不在任务栏 —— 不说清楚用户根本找不到它，
; 只能去任务管理器乱翻。所以这里点名两条具体路径。
zhcn.SetupAppRunningError=AI 提词器 正在运行，安装没法继续。%n%n安装要替换 python 运行时里的文件，程序开着的时候这些文件删不掉（会报「拒绝访问」，而且是每个文件弹一次）。%n%n请先退出提词器：%n    · 在控制台页面右上角点「退出程序」；%n    · 找不到控制台，就到任务管理器里结束 pythonw.exe。%n%n关掉之后点「确定」继续；点「取消」退出安装。
zhcn.UninstallAppRunningError=AI 提词器 正在运行，没法卸载。%n%n请先退出提词器（控制台右上角「退出程序」，或任务管理器里结束 pythonw.exe），再点「确定」。

[CustomMessages]
zhcn.CreateDesktopIcon=创建桌面快捷方式
zhcn.LaunchApp=立即启动 {#MyAppName}
zhcn.Troubleshoot=排查启动（带命令行窗口）


; ---------------------------------------------------------------------------
;  组件页：让用户选「怎么跑」。exclusive = 单选，选一个另一个自动取消。
;  这一步决定了要下 2.6 GB 还是 240 MB。
; ---------------------------------------------------------------------------
[Components]
; 父组件只是分组用的，Flags: fixed 让它不可取消，用户只能选下面两个之一。
; （Inno 要求子组件必须先有父组件，不能直接从 accel\cuda 开始写。）
Name: "accel";      Description: "运行方式（二选一）"; Types: full; Flags: fixed
Name: "accel\cuda"; Description: "NVIDIA 显卡加速（推荐）| 需下载约 2.6 GB；识别延迟约 0.25 秒，跟得上正常语速"; Types: full; Flags: exclusive
Name: "accel\cpu";  Description: "仅用 CPU| 只需下载约 240 MB；识别延迟约 1.2 秒，语速快时会有点跟不动"; Flags: exclusive


[Tasks]
Name: "desktopicon";   Description: "{cm:CreateDesktopIcon}";                            GroupDescription: "附加任务："
Name: "downloadmodel"; Description: "现在就下载语音识别模型（1.8 GB）| 不勾也可以，以后在程序里点一下就会下"; GroupDescription: "附加任务："


[Files]
; 整个 payload 原样铺到安装目录：
;   {app}\python\       embeddable Python + pip
;   {app}\app\          程序代码
;   {app}\web\          前端页面
;   {app}\assets\       图标
;   {app}\run.py        入口
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 用户数据的目录先建出来，省得程序第一次跑才创建。
; 不要写 Permissions: users-modify —— 那是给「装进 Program Files、需要放宽 ACL」
; 的场景准备的；本安装程序是 lowest 权限、装在自己 %LOCALAPPDATA% 下，
; 目录天生就是自己的，加了反而可能因为改不了 ACL 而失败。
[Dirs]
Name: "{app}\data"
Name: "{app}\models"
; 下载缓存 + 进度文件都落这里。放在安装目录下是为了不占 C 盘；
; 卸载时会连目录一起删掉（install.log 也在里面备查）。
Name: "{app}\_tmp"


[Icons]
; 快捷方式指向 pythonw.exe（不是 python.exe）—— 这样双击不弹黑框。
; 参数里把 run.py 的绝对路径传过去，工作目录设成 {app}，
; 因为 app/config.py 是按 __file__ 往上推 ROOT 的。
Name: "{group}\{#MyAppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\teleprompter.ico"; Comment: "启动 {#MyAppName}"
Name: "{group}\{cm:Troubleshoot}"; Filename: "{app}\start.bat"; IconFilename: "{app}\assets\teleprompter.ico"; Comment: "出问题时用这个启动，能看到报错"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\teleprompter.ico"; Tasks: desktopicon


[Run]
; Check: CanLaunchApp —— 依赖没装好时这一项直接不出现。
; 不然用户勾了「立即启动」，打开的窗口第一句就是"缺 fastapi/uvicorn"，很像程序坏了。
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent; Check: CanLaunchApp
; 打开的是摘要（几百字节），不是 install.log（30 MB）。
; ⛔ 不要用 shellexec：那是走系统关联，.log / .txt 关联到哪个程序完全看用户机器，
;    实测到过「窗口闪一下就没了」——用户什么都没看见。
;    直接点名 notepad.exe，结果可预期。
;    nowait：记事本是独立进程，安装器退出不该把它带走。
Filename: "{sys}\notepad.exe"; Parameters: """{app}\install-result.txt"""; Description: "查看安装结果"; Flags: postinstall nowait skipifsilent unchecked


; ===========================================================================
;  代码段
; ===========================================================================


[Code]
{ ===========================================================================
  这一版为什么把长任务搬出了 Inno 的窗口（2026-11-19 实测，别改回去）

  上一版在 CurStepChanged(ssPostInstall) 里跑一个 while 循环，每秒读一次
  状态文件、刷一次进度条和状态栏。用户看到的界面**确实在动**，但：

      · 点「取消」没反应
      · 点右上角最小化没反应
      · 点 ✕ 也没反应

  原因不是写错了，是 Inno 的机制：Pascal Script 执行期间，Inno **不派发
  输入消息**。界面之所以看起来在动，是因为我们每轮都调了 Label.Update
  强制重绘 —— 只有 WM_PAINT 被处理，鼠标和标题栏的点击根本进不了队列。
  换句话说：**在 Inno 的窗口里做不出能用的取消按钮**，怎么调都没用。

  所以现在的分工是：

      Inno（这个文件）        只管页面、复制文件、藏窗口、读结果
      tools\prep-ui.ps1       PowerShell + WinForms 的独立窗口，有真正的
                              消息循环 —— 最小化、关闭、暂停、取消全都能用
      tools\pip_progress.py   干活：下 wheel、跑 pip，把进度写进状态文件
      tools\download_model.py 干活：下模型
      tools\check_env.py      体检：决定哪几步可以整段跳过（增量安装）

  退出码约定（三处必须一致：本文件、prep-ui.ps1、两个 py 助手）
      0 = 成功     3 = 用户取消     4 = 失败 / 其它

  ⛔ 不要再往 CurStepChanged 里加长循环、也不要指望 WizardForm.CancelButton
     能点 —— 那两天已经证明过了。
  =========================================================================== }

const
  CRLF = #13#10;

var
  AppDir:     String;
  PythonExe:  String;
  LogPath:    String;
  ResultPath: String;
  TmpDir:     String;
  StatusFile: String;
  CancelFile: String;
  PauseFile:  String;
  PrepFile:   String;   { prep-ui.ps1 写的 ASCII 结果：state= / stage= / code= }
  PrepState:  String;   { ok / cancelled / failed }
  PrepStage:  String;
  PrepCode:   Integer;
  TorchChoice: String;  { cuda / cpu，传给进度窗口 }
  ModelChoice: String;  { 1 / 0 }
  TorchMode:  String;   { 给人看的说法，写进结果文件 }
  ModelOK:    Boolean;
  DepsReady:  Boolean;
  UserCancelled: Boolean;
  FailReason: String;


{ ------------------------------------------------------------------ 日志 }
{ ⚠️ 这里只写 ASCII。pip 追加的是 UTF-8，而 Inno 的 SaveStringToFile 按系统
  代码页（中文系统是 GBK）写 —— 同一份文件混两种编码，记事本打开就是乱码。
  全用 ASCII 就不会错。中文摘要另写 install-result.txt（整份都是 GBK）。 }
procedure Log(const S: String);
var
  F: String;
begin
  F := LogPath;
  if F = '' then
    F := ExpandConstant('{tmp}\aitp-install.log');
  SaveStringToFile(F, S + CRLF, True);
end;

procedure LogHeader(const S: String);
begin
  Log('');
  Log('==== ' + S + ' ====');
end;


{ ------------------------------------------------------------ 读结果文件 }

{ prep-ui.ps1 结束时会在 _tmp\prep-result.txt 留三行：
      state=ok|cancelled|failed
      stage=torch|rest|model|...
      code=0
  纯 ASCII，所以不用担心编码。读不到就当作失败 —— 宁可报错，
  也不要静悄悄地把「没装好」当成功。 }
function ReadPrepResult: Boolean;
var
  Lines: TArrayOfString;
  I: Integer;
  S: String;
begin
  Result := False;
  PrepState := '';
  PrepStage := '';
  PrepCode  := 0;
  if not FileExists(PrepFile) then
  begin
    Log('[WARN] prep-result.txt missing');
    Exit;
  end;
  if not LoadStringsFromFile(PrepFile, Lines) then
    Exit;

  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    S := Trim(Lines[I]);
    if CompareText(Copy(S, 1, 6), 'state=') = 0 then
      PrepState := Copy(S, 7, Length(S) - 6)
    else if CompareText(Copy(S, 1, 6), 'stage=') = 0 then
      PrepStage := Copy(S, 7, Length(S) - 6)
    else if CompareText(Copy(S, 1, 5), 'code=') = 0 then
      PrepCode := StrToIntDef(Copy(S, 6, Length(S) - 5), 0);
  end;
  Result := PrepState <> '';
  Log('prep state=' + PrepState + ' stage=' + PrepStage +
      ' code=' + IntToStr(PrepCode));
end;


{ ------------------------------------------------------------ 跑进度窗口 }

{ 这一步会阻塞（ewWaitUntilTerminated）。没关系 —— 向导已经被藏起来了，
  用户在交互的是 PowerShell 那个窗口。阻塞的只是 Inno 自己的消息循环。 }
procedure RunPrep(var RC: Integer);
var
  Ps, Params: String;
  T0: String;
begin
  DeleteFile(PrepFile);

  if not FileExists(AppDir + '\tools\prep-ui.ps1') then
  begin
    RC := -1;
    Log('[FAIL] tools\prep-ui.ps1 missing');
    Exit;
  end;

  (* 用 sys 常量而不是 sysnative：sys 在 64 位系统上会解析到 SysWOW64，
     但 WindowsPowerShell 那两个目录都有；sysnative 在 32 位系统上不存在。
     ⚠️ 这段注释不能用花括号写 —— 注释体里出现 {xxx} 会把注释提前闭合，
        编译报 "Syntax error"，行号还指在奇怪的位置。 *)
  Ps := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');

  Params :=
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden' +
    ' -File "' + AppDir + '\tools\prep-ui.ps1"' +
    ' -AppDir "' + AppDir + '"' +
    ' -Torch ' + TorchChoice +
    ' -Model ' + ModelChoice +
    ' -StatusFile "' + StatusFile + '"' +
    ' -LogFile "' + LogPath + '"' +
    ' -TmpDir "' + TmpDir + '"' +
    ' -CancelFile "' + CancelFile + '"' +
    ' -PauseFile "' + PauseFile + '"' +
    ' -ResultFile "' + PrepFile + '"';

  Log('[prep] ' + Ps);
  Log('[prep] ' + Params);

  { 记一下起止时刻。这一行是事后判断「进度窗口到底有没有真跑起来」的
    唯一硬证据：隔了几秒 = 正常；同一秒内就去又回 = 它根本没起来
    （比如被安全软件拦了，或者 -File 指向的脚本没落地），
    这时候 prep-result.txt 也不会存在。
    注：Pascal Script 里没有 GetTickCount，只能精确到秒。
        而且 GetDateTimeString 的第 2、3 个参数是 **Char** ——
        传 '' 会抛 "Type Mismatch"（实测踩过，整段 RunPrep 直接崩掉），
        不用日期分隔符就写 #0。 }
  T0 := GetDateTimeString('hh:nn:ss', #0, ':');
  if not Exec(Ps, Params, AppDir, SW_HIDE, ewWaitUntilTerminated, RC) then
  begin
    RC := -1;
    Log('[FAIL] cannot start powershell');
  end;
  Log('[prep] exit code ' + IntToStr(RC) + '  ' + T0 + ' -> ' +
      GetDateTimeString('hh:nn:ss', #0, ':'));
end;


{ ------------------------------------------------------------ 结果摘要 }

{ 几百字节的人话，完成页那个勾选项打开的就是它。
  install.log 有 30 MB，用户对着满屏 pip 日志看不出结论。 }
procedure WriteResultFile;
var
  S, Deps, ModelLine, Verdict: String;
begin
  if PrepState = 'ok' then
    Deps := '成功（PyTorch 和语音识别依赖都已就位）'
  else if PrepState = 'cancelled' then
    Deps := '你按了取消，没装完'
  else
    Deps := '失败（' + PrepStage + ' 这一步，退出码 ' + IntToStr(PrepCode) + '）';

  if ModelOK then
    ModelLine := '已就绪'
  else if not WizardIsTaskSelected('downloadmodel') then
    ModelLine := '没勾「现在就下载」—— 程序里点一下就会下'
  else
    ModelLine := '没下完 —— 不影响打开程序，可以在程序里重新下载';

  if PrepState = 'ok' then
    Verdict := '安装成功，双击桌面图标就能用。'
  else if PrepState = 'cancelled' then
    Verdict := '已取消。程序文件留着（约 13 MB），运行环境没装完；' + CRLF +
               '          重新运行安装程序会接着装，已下载的部分不会重来。'
  else
    Verdict := '程序文件装上了，但运行环境没齐，暂时跑不起来。' + CRLF +
               '          重新运行安装程序，它只会补缺的那部分。';

  S :=
    'AI 提词器  安装结果' + CRLF +
    '==============================================' + CRLF +
    '版本      {#MyAppVersion}' + CRLF +
    '安装目录  ' + AppDir + CRLF +
    '时间      ' + GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + CRLF +
    CRLF +
    '运行环境  ' + Deps + CRLF +
    'PyTorch   ' + TorchMode + CRLF +
    '模型      ' + ModelLine + CRLF +
    CRLF +
    '结论      ' + Verdict + CRLF +
    CRLF +
    '完整日志  ' + LogPath + CRLF +
    '          （pip 的细节都在里面，上面几行才是重点）' + CRLF;

  SaveStringToFile(ResultPath, S, False);
end;


{ -------------------------------------------------------------- 主流程 }

procedure CurStepChanged(CurStep: TSetupStep);
var
  RC: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;

  { 从这一步开始自己写日志（之前 Inno 自己的 SetupLogging 记在 %TEMP%）}
  SaveStringToFile(LogPath, '', False);
  Log('AITeleprompter installer log');
  Log('version {#MyAppVersion}');
  Log('time    ' + GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':'));
  Log('appdir  ' + AppDir);
  Log('python  ' + PythonExe);
  Log('torch   ' + TorchChoice + '   model ' + ModelChoice);

  if not FileExists(PythonExe) then
  begin
    FailReason := '安装包里没解出 python\python.exe，安装包可能损坏了。';
    Log('[FAIL] python.exe missing');
    PrepState := 'failed';
    MsgBox(FailReason + CRLF + CRLF + '检查路径：' + PythonExe, mbError, MB_OK);
    Exit;
  end;

  { 藏向导。不藏的话用户会同时看到两个窗口，后面那个（Inno 的）点不动 ——
    正是上一版被投诉的现象。 }
  try
    WizardForm.Hide;
  except
  end;

  RC := -1;
  try
    RunPrep(RC);
  except
    RC := -1;
    Log('[FAIL] exception: ' + GetExceptionMessage);
  end;

  try
    WizardForm.Show;
  except
  end;

  if not ReadPrepResult then
  begin
    { 读不到结果就按退出码猜：0 才算成功，别的都算没装完 }
    if RC = 0 then
      PrepState := 'ok'
    else if RC = 3 then
      PrepState := 'cancelled'
    else
      PrepState := 'failed';
    PrepStage := 'unknown';
    PrepCode  := RC;
  end;

  UserCancelled := (PrepState = 'cancelled');
  DepsReady     := (PrepState = 'ok');
  ModelOK       := (PrepState = 'ok') and WizardIsTaskSelected('downloadmodel');

  if PrepState = 'failed' then
  begin
    FailReason := '运行环境没装好（阶段 ' + PrepStage + '，退出码 ' + IntToStr(PrepCode) + '）。';
    Log('[FAIL] ' + FailReason);
  end;
  if UserCancelled then
    Log('[ABORT] cancelled by user');

  WriteResultFile;
  Log('result written: ' + ResultPath);
end;


{ 完成页：取消 / 失败时不能还写「安装完成」，那是骗人。
  这几行必须放在 CurPageChanged —— 页面文字是 Inno 在切页时才填的，
  在 CurStepChanged 里改会被覆盖掉。 }
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID <> wpFinished then
    Exit;

  if UserCancelled then
  begin
    try
      WizardForm.FinishedHeadingLabel.Caption := '安装已取消';
      WizardForm.FinishedLabel.Caption :=
        '运行环境没有装完，所以程序暂时还用不了。' + CRLF + CRLF +
        '已经下载的部分都保留着：重新运行安装程序，它会只补没完成的那部分，' +
        '不会从零开始。';
    except
    end;
  end
  else if (PrepState = 'failed') then
  begin
    try
      WizardForm.FinishedHeadingLabel.Caption := '安装未完成';
      WizardForm.FinishedLabel.Caption :=
        '程序文件装好了，但运行环境没齐（' + PrepStage + ' 这一步没过）。' + CRLF + CRLF +
        '重新运行安装程序可以只补缺的那部分。' + CRLF +
        '详细原因见安装目录下的 install.log。';
    except
    end;
  end;
end;


{ ------------------------------------------------------------ 准备阶段 }

{ 这个文件现在能不能被写？

  ⚠️ 只用 PowerShell 的 [IO.File]::Open 做一次「打开-关闭」，**不做任何写入**。
  为什么不用 Inno 自带的 FileOpen —— Inno 7 的 Pascal Script 里没有这个函数了
  （编译直接报 Unknown identifier）。也别用 SaveStringToFile 之类"顺手写点东西"
  的招：这个文件是 python313.dll，一次误截断就是装完打不开。

  为什么"能写"等于"没被占用"：程序开着时 DLL 被映射进内存，Windows 只允许
  只读共享，写打开必然失败。反过来写得开，就说明 Inno 待会儿删得掉。 }
function IsFileLocked(const Path: String): Boolean;
var
  Ps, Cmd: String;
  RC: Integer;
begin
  Result := True;                 { 判不准就当被占用：宁可多问一句，不要装到一半炸 }
  Ps := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  Cmd := '-NoProfile -NonInteractive -WindowStyle Hidden -Command ' +
    '"try { $f = [IO.File]::Open(''' + Path + ''', ''Open'', ''Write'', ''None'');' +
    ' $f.Close(); exit 0 } catch { exit 1 }"';
  if Exec(Ps, Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC) then
    Result := (RC <> 0);
end;

{ 安装前确认旧版本没在运行。返回 '' 表示可以装，否则是要显示给用户的说明。

  为什么 AppMutex 之外还要这一道：2.2.2 及更早的版本启动时根本没有创建那个
  互斥体。用户正开着旧版来装新版，AppMutex 什么也看不见 —— 于是又回到
  「每个被锁文件弹一次拒绝访问」。所以复制文件之前自己再探一遍。 }
function CheckAppNotRunning: String;
var
  Probe: array[0..2] of String;
  I: Integer;
begin
  Result := '';
  Probe[0] := AppDir + '\python\python313.dll';
  Probe[1] := AppDir + '\python\python.exe';
  Probe[2] := AppDir + '\python\pythonw.exe';

  for I := 0 to 2 do
  begin
    if FileExists(Probe[I]) and IsFileLocked(Probe[I]) then
    begin
      Result :=
        'AI 提词器 看起来还在运行，安装没法继续。' + #13#10 + #13#10 +
        '安装要替换 python 运行时里的文件，程序开着的时候这些文件删不掉。' + #13#10 + #13#10 +
        '请先退出提词器：' + #13#10 +
        '  · 在控制台页面右上角点「退出程序」；' + #13#10 +
        '  · 找不到控制台，就到任务管理器里结束 pythonw.exe。' + #13#10 + #13#10 +
        '关掉之后再点「下一步」。如果你确定已经关了，直接再点一次「下一步」重试。';
      Exit;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  AppDir    := ExpandConstant('{app}');
  PythonExe := AppDir + '\python\python.exe';
  LogPath   := AppDir + '\install.log';
  TmpDir    := AppDir + '\_tmp';
  { 进度文件放临时目录：它每秒被重写，不能留在安装目录根上干扰用户，
    也别放系统 TEMP（那是 C 盘）}
  StatusFile := TmpDir + '\progress.txt';
  { 三个暗号文件：取消、暂停、结果。改动要和 prep-ui.ps1 里的默认值一致 }
  CancelFile := TmpDir + '\cancel.flag';
  PauseFile  := TmpDir + '\pause.flag';
  PrepFile   := TmpDir + '\prep-result.txt';
  ResultPath := AppDir + '\install-result.txt';

  if WizardIsComponentSelected('accel\cpu') then
  begin
    TorchChoice := 'cpu';
    TorchMode   := '仅 CPU 版（约 240 MB）';
  end
  else
  begin
    TorchChoice := 'cuda';
    TorchMode   := '显卡加速版（CUDA 12.6，约 2.6 GB）';
  end;

  if WizardIsTaskSelected('downloadmodel') then
    ModelChoice := '1'
  else
    ModelChoice := '0';

  PrepState := '';
  PrepStage := '';
  PrepCode  := 0;
  ModelOK   := False;
  DepsReady := False;
  UserCancelled := False;
  { ⛔ 这里不写日志 —— 此刻安装目录还没建出来。
    但「文件有没有被占用」可以查：查的是**上一次装的那些文件**，不是新建。 }
  Result := CheckAppNotRunning();
end;

function CanLaunchApp: Boolean;
begin
  Result := DepsReady;
end;

{ ---------------------------------------------------------------- 卸载 }

function DirHasEntries(const Dir: String): Boolean;
var
  FindRec: TFindRec;
begin
  Result := False;
  if FindFirst(Dir + '\*', FindRec) then
  try
    repeat
      if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
      begin
        Result := True;
        Exit;
      end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir, ModelDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  { 下载缓存和进度文件，直接删 }
  DelTree(ExpandConstant('{app}\_tmp'), True, True, True);

  { 安装过程留下的两份文件：装完才有，不在 Files 列表里，
    不显式删就会在卸载后孤零零留在目录里 }
  DeleteFile(ExpandConstant('{app}\install.log'));
  DeleteFile(ExpandConstant('{app}\install-result.txt'));

  DataDir  := ExpandConstant('{app}\data');
  ModelDir := ExpandConstant('{app}\models');

  if DirExists(DataDir) and DirHasEntries(DataDir) then
    if MsgBox('要一并删除你写的稿子和界面设置吗？' + #13#10#13#10 + DataDir,
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(DataDir, True, True, True);

  if DirExists(ModelDir) and DirHasEntries(ModelDir) then
    if MsgBox('要一并删除语音识别模型吗？（1.8 GB，删了下次要重下）' + #13#10#13#10 + ModelDir,
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ModelDir, True, True, True);
end;
