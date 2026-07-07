@echo on
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM =========================================================
REM CONFIGURAÇÕES GERAIS
REM =========================================================
set "TOKEN=0be1d15273a396ac285ee0f7b9a625c8DAEAAD9FCFE96680781DDE57F45E774BF4B57C2D"
set "RESOURCE=400531375"
set "OBJECT=401810950"

set "MYSQL_HOST=127.0.0.1"
set "MYSQL_USER=root"
set "MYSQL_PASS=12345"
set "MYSQL_DB=telemetria_sorocaba"

REM Templates a executar
set "TEMPLATES=43 34 38 39 56 41 40 31 12 21"

REM =========================================================
REM DIRETÓRIO BASE
REM =========================================================
cd /d "%~dp0"

REM =========================================================
REM SCRIPT PYTHON
REM =========================================================
set "PY_SCRIPT=wialon_report_sorocaba.py.py"

if not exist "%PY_SCRIPT%" (
  echo ERRO: Script Python não encontrado: %PY_SCRIPT%
  exit /b 1
)

REM =========================================================
REM DATA FIXA (AJUSTE AQUI)
REM =========================================================
set "DATA=2026-07-03"

for /f "delims=" %%I in ('
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d = [datetime]::Parse('%DATA% 00:00:00'); $d = $d.AddHours(3); $d.ToString('yyyy-MM-dd HH:mm:ss')"
') do set "FROM=%%~I"

for /f "delims=" %%I in ('
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d = [datetime]::Parse('%DATA% 23:59:59'); $d = $d.AddHours(3); $d.ToString('yyyy-MM-dd HH:mm:ss')"
') do set "TO=%%~I"

echo FROM=!FROM!
echo TO=!TO!

REM =========================================================
REM LOG
REM =========================================================
set "LOGFILE=wialon_pernambucanas_log.txt"
echo ==== START %DATE% %TIME% ====>>"%LOGFILE%"
echo Janela: !FROM! -> !TO!>>"%LOGFILE%"

REM =========================================================
REM LOOP DE TEMPLATES
REM =========================================================
for %%T in (%TEMPLATES%) do call :RUN_TEMPLATE %%T

echo ==== FIM %DATE% %TIME% ====>>"%LOGFILE%"
echo.
echo TODOS OS RELATÓRIOS FINALIZADOS. Veja "%LOGFILE%"
pause
exit /b 0

REM =========================================================
REM FUNÇÃO EXECUTAR TEMPLATE
REM =========================================================
:RUN_TEMPLATE
set "TPL=%~1"

echo ---------------------------------------->>"%LOGFILE%"
echo Rodando Template %TPL% em %DATE% %TIME%>>"%LOGFILE%"
echo Rodando Template %TPL%...

py "%PY_SCRIPT%" ^
  --token "%TOKEN%" ^
  --resource-id %RESOURCE% ^
  --template-id %TPL% ^
  --object-id %OBJECT% ^
  --from "%FROM%" --to "%TO%" ^
  --format xlsx ^
  --output "Relatorio_Wialon_%TPL%_%DATA%" ^
  --mysql-host "%MYSQL_HOST%" ^
  --mysql-user "%MYSQL_USER%" ^
  --mysql-pass "%MYSQL_PASS%" ^
  --mysql-db "%MYSQL_DB%" ^
  --timeout 3600 --http-timeout 1200 --verbose ^
  >>"%LOGFILE%" 2>&1

set "RC=%ERRORLEVEL%"
echo ExitCode=%RC%>>"%LOGFILE%"

if "%RC%"=="0" (
  echo Template %TPL% concluído com sucesso!>>"%LOGFILE%"
) else (
  echo ERRO no Template %TPL% (codigo %RC%)>>"%LOGFILE%"
)

exit /b
