@echo off
REM Ouvre l'Universite MGC dans le navigateur (le serveur tourne sans fenetre noire, sur ce PC seulement)
REM Recherche et simulation seulement : aucun ordre, aucun courtier.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo TradingAgents n'est pas installe : lance d'abord "1 - INSTALLER.bat".
  pause
  exit /b 1
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
start "" ".venv\Scripts\pythonw.exe" -m universite
