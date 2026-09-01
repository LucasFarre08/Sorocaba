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
set "TEMPLATES=43 34 38 39 56 41 40 31 12 21 114"

cd /d "%~dp0"

REM ==== Intervalo das ÚLTIMAS 12 HORAS (ajuste de fuso Brasil UTC-3 → UTC) ====
for /f "delims=" %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Date).AddHours(3).AddHours(-12).ToString('yyyy-MM-dd HH:mm:ss')"') do set "FROM=%%~I"
for /f "delims=" %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Date).AddHours(3).ToString('yyyy-MM-dd HH:mm:ss')"') do set "TO=%%~I"

echo FROM=!FROM!
echo TO=!TO!

if "!FROM!"=="" (
    echo ERRO: FROM veio vazio. Verifique o PowerShell.
    pause
    exit /b 1
)
if "!TO!"=="" (
    echo ERRO: TO veio vazio. Verifique o PowerShell.
    pause
    exit /b 1
)

set "LOGFILE=wialon_sorocaba_log.txt"
echo ==== INICIO %DATE% %TIME% ====>> "%LOGFILE%"
echo Janela: !FROM! -^> !TO!>> "%LOGFILE%"

REM ===== Loop chamando sub-rotina =====
for %%T in (%TEMPLATES%) do call :RUN_TEMPLATE %%T

echo ==== FIM %DATE% %TIME% ====>> "%LOGFILE%"
echo.
echo TODOS OS RELATORIOS FORAM EXECUTADOS. Veja "%LOGFILE%" para detalhes.
pause
exit /b 0

:RUN_TEMPLATE
set "TPL=%~1"
echo ------------------------------------------>> "%LOGFILE%"
echo Rodando Template %TPL% em %DATE% %TIME% >> "%LOGFILE%"
echo Rodando Template %TPL%...

py wialon_report_consigaz.py.py ^
  --token "%TOKEN%" ^
  --resource-id %RESOURCE% ^
  --template-id %TPL% ^
  --object-id %OBJECT% ^
  --from "!FROM!" --to "!TO!" ^
  --format xlsx --output Relatorio_Wialon_%TPL% ^
  --mysql-host "%MYSQL_HOST%" ^
  --mysql-user "%MYSQL_USER%" ^
  --mysql-pass "%MYSQL_PASS%" ^
  --mysql-db "%MYSQL_DB%" ^
  --timeout 3600 --http-timeout 1200 --verbose ^
  >> "%LOGFILE%" 2>&1

set "RC=%ERRORLEVEL%"
echo Codigo de saida (Template %TPL%): %RC%>> "%LOGFILE%"

if "%RC%"=="0" (
    echo Template %TPL% concluido com sucesso! >> "%LOGFILE%"
) else (
    echo ERRO no Template %TPL% ^(codigo %RC%^). Veja "%LOGFILE%".
    echo ERRO no Template %TPL% ^(codigo %RC%^). >> "%LOGFILE%"
)
exit /b %RC%