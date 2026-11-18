@echo off
chcp 65001 >nul
title AI Teleprompter - first time setup
cd /d "%~dp0"

rem ===========================================================================
rem  Run this ONCE on a new machine, before start.bat.
rem  Creates a local .venv and installs the pinned dependencies into it.
rem  Everything stays inside this folder - nothing is installed system-wide.
rem
rem  IMPORTANT - keep this file pure ASCII. cmd.exe reads a .bat by BYTE OFFSET;
rem  non-ASCII characters make it jump into the middle of a multi-byte char and
rem  execute garbage. See the note in start.bat.
rem ===========================================================================

echo.
echo   AI Teleprompter - setup
echo   ---------------------------------------------
echo   This will create .venv\ and install dependencies.
echo   Keep this window open. It can take 5-15 minutes.
echo.

rem ---- 1. find a Python 3.10+ ------------------------------------------------
rem  Do NOT write "if not defined PY where python && set ..." - the && would bind
rem  to the whole if-statement and clobber an already-chosen interpreter.
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [x] Python not found.
    echo     Install Python 3.10 or newer from https://www.python.org/downloads/
    echo     and tick "Add python.exe to PATH" during the install.
    echo.
    pause
    exit /b 1
)

echo [1/4] using: %PY%
%PY% -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)"
if errorlevel 1 (
    echo [x] Python is too old. Need 3.10 or newer.
    pause
    exit /b 1
)

rem ---- 2. create venv --------------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo [2/4] .venv already exists, reusing it
) else (
    echo [2/4] creating .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [x] Failed to create .venv
        pause
        exit /b 1
    )
)

set "VPY=.venv\Scripts\python.exe"

echo       upgrading pip ...
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check

rem ---- 3. torch, before requirements.txt -------------------------------------
rem  requirements.txt only says "torch>=2.4", so a plain pip run would pull the
rem  CPU build from PyPI. Pick explicitly here instead, otherwise the CUDA wheel
rem  never gets installed and people wonder why it is slow.
echo.
echo [3/4] torch - the compute engine
echo         CUDA build : ~2.5 GB, needs an NVIDIA GPU, about 10x faster
echo         CPU  build : ~200 MB, runs anywhere, slower but fine
echo.
set "CUDA="
set /p CUDA="Install the CUDA build? [y/N] "
if /i "%CUDA%"=="y" (
    echo       downloading torch (cu126) - this is the big one, be patient ...
    "%VPY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu126 --disable-pip-version-check
) else (
    echo       installing CPU build ...
    "%VPY%" -m pip install torch --index-url https://mirrors.ustc.edu.cn/pypi/simple --disable-pip-version-check
)
if errorlevel 1 (
    echo.
    echo [x] torch install failed. Scroll up for the reason.
    echo     For the CUDA build the mirror is https://download.pytorch.org/whl/cu126
    pause
    exit /b 1
)

rem ---- 4. the rest -----------------------------------------------------------
echo.
echo [4/4] installing requirements.txt ...
echo       ^(versions are pinned on purpose - do NOT "upgrade" them^)
echo.
"%VPY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [!] default index failed, retrying with the USTC mirror ...
    echo.
    "%VPY%" -m pip install -r requirements.txt --disable-pip-version-check --index-url https://mirrors.ustc.edu.cn/pypi/simple
)
if errorlevel 1 (
    echo.
    echo [x] pip install failed. Scroll up for the reason.
    pause
    exit /b 1
)

rem ---- verify before declaring victory ---------------------------------------
echo.
echo verifying the install ...
"%VPY%" -c "import fastapi, uvicorn, numpy, sounddevice, pypinyin, torch, transformers; print('  ok - torch', torch.__version__, '| cuda', torch.cuda.is_available())"
if errorlevel 1 (
    echo [x] Verification failed - something above did not install cleanly.
    pause
    exit /b 1
)

rem ---- optional: model weights ----------------------------------------------
echo.
if exist "models\Qwen3-ASR-0.6B\model.safetensors" (
    echo [ok] ASR model already present, nothing to download.
) else (
    echo ASR model not found ^(models\Qwen3-ASR-0.6B^).
    set /p DL="Download it now? 1.8 GB from ModelScope [Y/n] "
    if /i not "%DL%"=="n" (
        "%VPY%" tools\download_model.py
    ) else (
        echo skipped - the UI still works, speech following will not.
    )
)

echo.
echo =============================================
echo   Setup done. Double-click start.bat to run.
echo =============================================
echo.
pause
