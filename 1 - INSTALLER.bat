@echo off
REM Installation de TradingAgents (version du 3 oct. 2026, commit 1394a3f)
REM Tout s'installe dans ce dossier : rien d'autre n'est modifie sur le PC.
setlocal EnableExtensions
title Installation TradingAgents
cd /d "%~dp0"
set "DOSSIER=%~dp0"
set "LOG=%~dp0install_log.txt"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "COMMIT=1394a3f72aa4393e1a98f51b382434c4b4c2d972"
echo Installation demarree le %date% a %time% > "%LOG%"

echo.
echo  ==========================================
echo     Installation de TradingAgents
echo  ==========================================
echo  Ne ferme pas cette fenetre. Compte 5 a 15 minutes.
echo.

REM --- Etape 0 : trouver Python ---
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY (
  echo [ERREUR] Python introuvable >> "%LOG%"
  echo  [ERREUR] Python est introuvable sur ce PC. Dis-le a Claude.
  goto :fin_erreur
)
echo Python utilise : %PY% >> "%LOG%"
%PY% --version >> "%LOG%" 2>&1

REM --- Etape 1 : outil uv (gere une bulle Python 3.13 isolee) ---
echo  [1/6] Installation de l'outil d'installation (uv)...
echo ---- ETAPE 1 : uv >> "%LOG%"
%PY% -m pip install --user --upgrade uv >> "%LOG%" 2>&1
if errorlevel 1 (
  %PY% -m ensurepip --user >> "%LOG%" 2>&1
  %PY% -m pip install --user --upgrade uv >> "%LOG%" 2>&1
  if errorlevel 1 goto :erreur
)

REM --- Etape 2 : telecharger le code depuis GitHub ---
echo  [2/6] Telechargement de TradingAgents depuis GitHub...
echo ---- ETAPE 2 : telechargement >> "%LOG%"
set "TMPZ=%TEMP%\tradingagents_%COMMIT%.zip"
set "TMPX=%TEMP%\tradingagents_extract_%COMMIT%"
curl.exe -L --fail -sS -o "%TMPZ%" "https://github.com/TauricResearch/TradingAgents/archive/%COMMIT%.zip" >> "%LOG%" 2>&1
if errorlevel 1 goto :erreur
if not exist "%TMPX%" mkdir "%TMPX%"
tar -xf "%TMPZ%" -C "%TMPX%" >> "%LOG%" 2>&1
if errorlevel 1 goto :erreur
set "SRC="
for /d %%D in ("%TMPX%\TradingAgents-*") do set "SRC=%%D"
if not defined SRC goto :erreur
REM Copie dans ce dossier, sans jamais ecraser un .env existant
robocopy "%SRC%" "%DOSSIER%." /E /XF .env /NFL /NDL /NJH /NJS /NP >> "%LOG%"
if errorlevel 8 goto :erreur

REM --- Etape 3 : bulle Python 3.13 ---
echo  [3/6] Creation de la bulle Python 3.13 (isolee du reste du PC)...
echo ---- ETAPE 3 : venv >> "%LOG%"
if not exist ".venv\Scripts\python.exe" (
  %PY% -m uv venv --python 3.13 .venv >> "%LOG%" 2>&1
  if errorlevel 1 goto :erreur
)

REM --- Etape 4 : dependances ---
echo  [4/6] Installation des dependances (le plus long, patience)...
echo ---- ETAPE 4 : dependances >> "%LOG%"
%PY% -m uv pip install --python ".venv\Scripts\python.exe" . openpyxl >> "%LOG%" 2>&1
if errorlevel 1 goto :erreur

REM --- Etape 5 : fichier .env (la cle API, c'est toi qui la colles) ---
echo  [5/6] Preparation du fichier de reglages .env...
echo ---- ETAPE 5 : .env >> "%LOG%"
if not exist ".env" (
  copy ".env.example" ".env" >nul
  >> ".env" echo.
  >> ".env" echo # Reglages ajoutes par Claude, conseilles par le guide
  >> ".env" echo TRADINGAGENTS_OUTPUT_LANGUAGE=French
  >> ".env" echo TRADINGAGENTS_TEMPERATURE=0.0
  echo .env cree >> "%LOG%"
) else (
  echo .env deja present, pas touche >> "%LOG%"
)

REM --- Etape 6 : verification + raccourcis sur le Bureau ---
echo  [6/6] Verification et raccourcis sur le Bureau...
echo ---- ETAPE 6 : verification >> "%LOG%"
".venv\Scripts\tradingagents.exe" --help >> "%LOG%" 2>&1
if errorlevel 1 goto :erreur
".venv\Scripts\python.exe" -c "import tradingagents, openpyxl; print('import OK', tradingagents.__version__)" >> "%LOG%" 2>&1
if errorlevel 1 goto :erreur
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; foreach($p in @(@('TradingAgents','Lancer TradingAgents.bat'),@('TradingAgents - 3 analyses','Lancer 3 analyses.bat'))){ $s=$w.CreateShortcut((Join-Path $d ($p[0]+'.lnk'))); $s.TargetPath=(Join-Path '%DOSSIER%' $p[1]); $s.WorkingDirectory='%DOSSIER%'; $s.Save() }" >> "%LOG%" 2>&1

echo INSTALLATION OK >> "%LOG%"
echo.
echo  ==========================================
echo     INSTALLATION TERMINEE
echo  ==========================================
echo  Deux raccourcis sont sur ton Bureau :
echo    - TradingAgents             (l'outil complet)
echo    - TradingAgents - 3 analyses (le test de consensus)
echo  Tu peux fermer cette fenetre et prevenir Claude.
echo.
pause
exit /b 0

:erreur
echo ECHEC >> "%LOG%"
echo.
echo  [ERREUR] Quelque chose a bloque.
echo  Previens Claude : il lira le fichier install_log.txt.
:fin_erreur
echo.
pause
exit /b 1
