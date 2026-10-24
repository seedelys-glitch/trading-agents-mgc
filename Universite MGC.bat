@echo off
REM Ouvre l'Universite MGC dans le navigateur (le serveur tourne sans fenetre noire, sur ce PC seulement)
REM Recherche et simulation seulement : aucun ordre, aucun courtier.
REM Si une ANCIENNE version tourne encore (pas de bureau), elle est fermee puis la nouvelle est lancee.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo TradingAgents n'est pas installe : lance d'abord "1 - INSTALLER.bat".
  pause
  exit /b 1
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://127.0.0.1:8780/api/a_jour'; if ($r.StatusCode -eq 200) { exit 0 } } catch {} ; Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | Where-Object { $_.CommandLine -like '*-m universite*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } ; exit 1"
if %errorlevel%==0 (
  start "" "http://127.0.0.1:8780/"
  exit /b 0
)
timeout /t 2 /nobreak >nul
start "" ".venv\Scripts\pythonw.exe" -m universite
