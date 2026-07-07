@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ====== CONFIGURAÇÕES GERAIS ======
set "TOKEN=0be1d15273a396ac285ee0f7b9a625c8DAEAAD9FCFE96680781DDE57F45E774BF4B57C2D"
set "RESOURCE=400531375"
set "OBJECT=401149512"
set "MYSQL_HOST=127.0.0.1"
set "MYSQL_USER=root"
set "MYSQL_PASS=12345"
set "MYSQL_DB=telemetria_db"

REM Templates para executar:
set "TEMPLATES=21 "

cd /d "%~dp0"

REM ==== Intervalo do DIA ANTERIOR em TIMESTAMP Unix ====
for /f "delims=" %%I in ('
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Date).AddDays(-1).Date.ToUniversalTime().Subtract([datetime]'1970-01-01').TotalSeconds"
') do set "FROM_TS=%%~I"

for /f "delims=" %%I in ('
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Date).AddDays(-1).Date.AddHours(23).AddMinutes(59).AddSeconds(59).ToUniversalTime().Subtract([datetime]'1970-01-01').TotalSeconds"
') do set "TO_TS=%%~I"

echo FROM_TS=!FROM_TS!
echo TO_TS=!TO_TS!

REM Verifica se Python está disponível
where py >nul 2>&1 || (
    echo ERRO: Python não encontrado.
    pause
    exit /b 1
)

echo ==== INÍCIO %DATE% %TIME% ====>> "wialon_log.txt"
echo Janela: !FROM_TS! -> !TO_TS!>> "wialon_log.txt"

REM ===== Loop chamando sub-rotina =====
for %%T in (%TEMPLATES%) do call :RUN_TEMPLATE %%T

echo ==== FIM %DATE% %TIME% ====>> "wialon_log.txt"
echo.
echo TODOS OS RELATÓRIOS FORAM EXECUTADOS. Veja os logs individuais.
pause
exit /b 0


REM ========= Sub-rotina =========
:RUN_TEMPLATE
set "TPL=%~1"
set "LOGFILE=wialon_log_!TPL!.txt"

echo ------------------------------------------>> "!LOGFILE!"
echo Rodando Template !TPL! em %DATE% %TIME% >> "!LOGFILE!"
echo Rodando Template !TPL!...

py wialon_report_sql.py ^
    --token "!TOKEN!" ^
    --resource "!RESOURCE!" ^
    --object "!OBJECT!" ^
    --template "!TPL!" ^
    --from "!FROM_TS!" ^
    --to "!TO_TS!" ^
    --mysql-host "!MYSQL_HOST!" ^
    --mysql-user "!MYSQL_USER!" ^
    --mysql-pass "!MYSQL_PASS!" ^
    --mysql-db "!MYSQL_DB!" ^
    >> "!LOGFILE!" 2>&1

set "RC=!ERRORLEVEL!"
echo Código de saída (Template !TPL!): !RC!>> "!LOGFILE!"

REM Corrigido: IF em linha única para evitar erro
if "!RC!"=="0" (
    echo [OK] Template !TPL! concluído com sucesso! >> "!LOGFILE!"
    echo [OK] Template !TPL! concluído com sucesso!
) else (
    echo [ERRO] no Template !TPL! (código !RC!). Veja "!LOGFILE!". >> "!LOGFILE!"
    echo [ERRO] no Template !TPL! (código !RC!). Veja "!LOGFILE!".
)

goto :eof