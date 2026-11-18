@echo off
chcp 65001 >nul
title AI Teleprompter
cd /d "%~dp0"

rem ===========================================================================
rem  IMPORTANT - keep this file pure ASCII.
rem  cmd.exe reads a .bat by BYTE OFFSET. Non-ASCII characters here (even with
rem  "chcp 65001" above) make cmd jump into the middle of a multi-byte char and
rem  execute garbage, producing bogus errors like "system cannot find the path".
rem  All user-facing Chinese text lives in run.py, which prints it correctly.
rem ===========================================================================

rem ---- pick a python, in order of preference --------------------------------
rem   1) .venv\Scripts\python.exe   local venv created by setup.bat  (best)
rem   2) %TELEPROMPTER_PYTHON%      interpreter you pinned explicitly
rem   3) python in PATH             system python
rem
rem To pin an interpreter installed elsewhere, run this once:
rem     setx TELEPROMPTER_PYTHON "D:\path\to\python.exe"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if defined TELEPROMPTER_PYTHON set "PY=%TELEPROMPTER_PYTHON%"
if not defined PY set "PY=python"

echo [launcher] python = %PY%
echo.

rem ---- does that interpreter exist at all? ----------------------------------
"%PY%" -c "import sys" >nul 2>nul
if errorlevel 1 goto NOPY

rem ---- hand over to run.py: it checks deps and explains fixes in Chinese -----
"%PY%" run.py
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo [launcher] python exited with code %RC%
    pause
    exit /b 1
)
exit /b 0

:NOPY
echo.
echo [x] No working Python interpreter found.
echo     Tried, in order: .venv\Scripts\python.exe , TELEPROMPTER_PYTHON , python
echo.
echo     Install Python 3.13 from https://www.python.org/downloads/
echo     and tick "Add python.exe to PATH" while installing.
echo     Then run setup.bat once, and start.bat afterwards.
echo.
pause
exit /b 1
