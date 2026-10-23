@echo off
REM Ouvre la Salle des marches dans le navigateur (le serveur tourne sans fenetre noire)
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo TradingAgents n'est pas installe : lance d'abord "1 - INSTALLER.bat".
  pause
  exit /b 1
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM Premier lancement : raccourci "Salle des marches" sur le Bureau, avec son icone
if not exist "salle_des_marches\raccourci_cree.txt" (
  powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $d 'Salle des marches.lnk')); $s.TargetPath='%~dp0Salle des marches.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0salle_des_marches\salle.ico'; $s.WindowStyle=7; $s.Description='TradingAgents avec plusieurs IA'; $s.Save()" >nul 2>&1
  echo ok > "salle_des_marches\raccourci_cree.txt"
)

start "" ".venv\Scripts\pythonw.exe" "salle_des_marches\serveur.py"
