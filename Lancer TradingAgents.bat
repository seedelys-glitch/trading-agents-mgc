@echo off
REM Lance l'outil TradingAgents complet (le CLI interactif du guide)
title TradingAgents
cd /d "%~dp0"
if not exist ".venv\Scripts\tradingagents.exe" (
  echo TradingAgents n'est pas encore installe : lance d'abord "1 - INSTALLER.bat".
  pause
  exit /b 1
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul
".venv\Scripts\tradingagents.exe"
echo.
pause
