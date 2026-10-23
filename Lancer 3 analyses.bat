@echo off
REM Lance 3 analyses sur le meme ticker et compare les verdicts (consensus)
title TradingAgents - 3 analyses
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo TradingAgents n'est pas encore installe : lance d'abord "1 - INSTALLER.bat".
  pause
  exit /b 1
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul
".venv\Scripts\python.exe" "trois_analyses.py"
echo.
pause
