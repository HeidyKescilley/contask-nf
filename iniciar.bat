@echo off
setlocal
title Contask NF
cd /d "%~dp0"
set "PORTA=8765"
set "URL=http://127.0.0.1:%PORTA%"

rem Ja esta rodando? So abre o navegador.
call :saude 1
if %errorlevel%==0 goto abrir

rem Ambiente Python
if not exist ".venv\Scripts\python.exe" (
  echo Preparando o ambiente Python pela primeira vez...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 goto erro_python
  ".venv\Scripts\python.exe" -m pip install -q -r backend\requirements.txt
  if errorlevel 1 goto erro_python
)

rem Frontend compilado
if not exist "frontend\dist\index.html" (
  echo Compilando a interface pela primeira vez...
  pushd frontend
  if not exist node_modules call npm ci
  call npm run build
  popd
  if not exist "frontend\dist\index.html" goto erro_front
)

echo Iniciando o Contask NF...
start "Contask NF - servidor (feche para encerrar)" /min ".venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port %PORTA%

call :saude 40
if errorlevel 1 goto erro_servidor

:abrir
start "" "%URL%"
exit /b 0

:saude
powershell -NoProfile -Command "for($i=0;$i -lt %1;$i++){try{Invoke-WebRequest -UseBasicParsing '%URL%/api/saude' -TimeoutSec 1 | Out-Null; exit 0}catch{Start-Sleep -Milliseconds 500}}; exit 1"
exit /b %errorlevel%

:erro_python
echo.
echo Nao foi possivel preparar o Python. Instale o Python 3.14 e tente de novo.
pause
exit /b 1

:erro_front
echo.
echo Nao foi possivel compilar a interface. Verifique se o Node.js esta instalado.
pause
exit /b 1

:erro_servidor
echo.
echo O servidor nao respondeu. Veja a janela "Contask NF - servidor" para o erro.
pause
exit /b 1
