@echo on
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ====== CONFIGURAÇÕES GERAIS ======
set "TOKEN=0be1d15273a396ac285ee0f7b9a625c8DAEAAD9FCFE96680781DDE57F45E774BF4B57C2D"
set "RESOURCE=400531375"
set "OBJECT=400603989"
set "MYSQL_HOST=127.0.0.1"
set "MYSQL_USER=root"
set "MYSQL_PASS=12345"
set "MYSQL_DB=telemetria_db"

REM Templates para executar:
REM 29 = clia
REM 87 = filial entrada
REM 88 = operadores portuarios
set "TEMPLATES=29 87 88"
REM ============================

cd /d "%~dp0"

REM ==== Intervalo do DIA ANTERIOR (00:00:00 -> 23:59:59) ====
for /f "delims=" %%I in ('
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Date).AddDays(-1).Date.ToString('yyyy-MM-dd 00:00:00')"
') do set "FROM=%%~I"

for /f "delims=" %%I in ('
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Date).AddDays(-1).Date.AddHours(23).AddMinutes(59).AddSeconds(59).ToString('yyyy-MM-dd HH:mm:ss')"
') do set "TO=%%~I"

echo FROM=!FROM!
echo TO=!TO!

set "LOGFILE=wialon_log.txt"
echo ==== INÍCIO %DATE% %TIME% ====>> "%LOGFILE%"
echo Janela: !FROM! -> !TO!>> "%LOGFILE%"

REM ===== Loop chamando sub-rotina (sem parênteses) =====
for %%T in (%TEMPLATES%) do call :RUN_TEMPLATE %%T

echo ==== FIM %DATE% %TIME% ====>> "%LOGFILE%"
echo.
echo TODOS OS RELATÓRIOS FORAM EXECUTADOS. Veja "%LOGFILE%" para detalhes.
pause
exit /b 0


REM ========= Sub-rotina sem parênteses/ELSE =========
:RUN_TEMPLATE
set "TPL=%~1"
echo ------------------------------------------>> "%LOGFILE%"
echo Rodando Template %TPL% em %DATE% %TIME% >> "%LOGFILE%"
echo Rodando Template %TPL%...

py wialon_report_sql.py ^
  --token "%TOKEN%" ^
  --resource-id %RESOURCE% ^
  --template-id %TPL% ^
  --object-id %OBJECT% ^
  --from "%FROM%" --to "%TO%" ^
  --format xlsx --output Relatorio_Wialon_%TPL% ^
  --mysql-host "%MYSQL_HOST%" --mysql-user "%MYSQL_USER%" --mysql-pass "%MYSQL_PASS%" --mysql-db "%MYSQL_DB%" ^
  --timeout 3600 --http-timeout 1200 --verbose ^
  >> "%LOGFILE%" 2>&1

set "RC=%ERRORLEVEL%"
echo Código de saída (Template %TPL%): %RC%>> "%LOGFILE%"

if "%RC%"=="0" goto :OK_%TPL%
echo ERRO no Template %TPL% (código %RC%). Veja "%LOGFILE%".
goto :END_%TPL%

:OK_%TPL%
echo Template %TPL% concluído com sucesso! >> "%LOGFILE%"

:END_%TPL%
exit /b