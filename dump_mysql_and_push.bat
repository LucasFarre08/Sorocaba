@echo off
setlocal

REM ======= CONFIG =======
set "MYSQL_BIN=C:\Program Files\MySQL\MySQL Server 8.0\bin"
set "DB_HOST=127.0.0.1"
set "DB_USER=root"
set "DB_PASS=12345"
set "DB_NAME=telemetria_db"
set "DUMPS_DIR=dumps"
set "KEEP=7"  REM quantos dumps manter
set "GIT_EXE=C:\Users\lucas.farre\AppData\Local\Programs\Git\cmd\git.exe"


REM ======= PREP =======
cd /d "%~dp0"
if not exist "%DUMPS_DIR%" mkdir "%DUMPS_DIR%"

if not exist "%GIT_EXE%" (
  echo [ERRO] Nao encontrei %GIT_EXE%. Instale o Git for Windows ou ajuste o caminho.
  exit /b 1
)

REM timestamp seguro
for /f "delims=" %%I in ('
  powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd_HHmmss')"
') do set "STAMP=%%I"

set "OUT=%DUMPS_DIR%\%DB_NAME%_%STAMP%.sql"
set "LATEST=%DUMPS_DIR%\%DB_NAME%_latest.sql"

REM ======= TESTE mysqldump =======
"%MYSQL_BIN%\mysqldump.exe" --version >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Nao encontrei mysqldump em "%MYSQL_BIN%".
  exit /b 1
)

REM ======= DUMP (UTF-8 + credenciais via arquivo temporario) =======
echo [INFO] Gerando dump em "%OUT%"...

set "CFG=%TEMP%\mydump_%RANDOM%.cnf"
(
  echo [client]
  echo host=%DB_HOST%
  echo user=%DB_USER%
  echo password=%DB_PASS%
  echo default-character-set=utf8mb4
)>"%CFG%"

"%MYSQL_BIN%\mysqldump.exe" ^
  --defaults-extra-file="%CFG%" ^
  --routines --events --triggers --single-transaction ^
  --databases %DB_NAME% > "%OUT%"
set "RC=%ERRORLEVEL%"

del /f /q "%CFG%" >nul 2>&1

if not "%RC%"=="0" (
  echo [ERRO] mysqldump falhou. Codigo %RC%.
  exit /b %RC%
)

REM ======= ATUALIZA 'latest' =======
copy /Y "%OUT%" "%LATEST%" >nul

REM ======= ROTACAO (CMD puro): manter apenas %KEEP% arquivos mais recentes =======
if "%KEEP%"=="0" goto :SKIP_ROTATE
setlocal EnableDelayedExpansion
set "COUNT=0"
for /f "delims=" %%F in ('dir /b /o-d "%DUMPS_DIR%\%DB_NAME%_*.sql" 2^>nul') do (
  set /a COUNT+=1
  if !COUNT! gtr %KEEP% (
    del /f /q "%DUMPS_DIR%\%%F"
  )
)
endlocal
:SKIP_ROTATE

REM ======= GIT: pull + add + commit + push =======
"%GIT_EXE%" pull --rebase origin main 2>nul
"%GIT_EXE%" add "%OUT%" "%LATEST%" "%DUMPS_DIR%\README.md" .gitignore
"%GIT_EXE%" diff --cached --quiet
if %errorlevel%==0 (
  echo [INFO] Nada novo para enviar.
  exit /b 0
)
"%GIT_EXE%" commit -m "dump(%DB_NAME%): %STAMP%"
"%GIT_EXE%" push

echo [OK] Dump enviado: %OUT%
exit /b 0
