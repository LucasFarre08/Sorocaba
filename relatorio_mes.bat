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

set "TEMPLATES=43 34 38 39 56 41 40 31 12 21"

REM =========================================================
REM DIRETÓRIO BASE
REM =========================================================
cd /d "%~dp0"

set "LOGFILE=wialon_sorocaba_log.txt"

REM =========================================================
REM SCRIPT PYTHON (OBRIGATÓRIO EXISTIR)
REM =========================================================
set "PY_SCRIPT=%~dp0wialon_report_sorocaba.py.py"

if not exist "%PY_SCRIPT%" (
  echo ERRO: Script Python nao encontrado: %PY_SCRIPT%
  echo ERRO: Script Python nao encontrado: %PY_SCRIPT%>>"%LOGFILE%"
  exit /b 1
)

echo ==== START (Selected Month) %DATE% %TIME% ====>>"%LOGFILE%"

REM =========================================================
REM PARÂMETROS
REM =========================================================
set "INPUT_MONTH=%~1"
set "INPUT_YEAR=%~2"
set "INPUT_THIRD=%~3"

if "%INPUT_MONTH%"=="" set /p INPUT_MONTH=Digite o mês (1-12):
if "%INPUT_YEAR%"==""  set /p INPUT_YEAR=Digite o ano (ex: 2026):

set "SINGLE_DAY="
set "KEEP_FOLDER=0"

if not "%INPUT_THIRD%"=="" (
  if /I "%INPUT_THIRD%"=="keep" (
    set "KEEP_FOLDER=1"
  ) else (
    echo %INPUT_THIRD%|findstr /r "^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$" >nul
    if not errorlevel 1 set "SINGLE_DAY=%INPUT_THIRD%"
  )
)

REM =========================================================
REM VALIDAÇÕES
REM =========================================================
set /a MNUM=%INPUT_MONTH% 2>nul || goto :INVALID_MONTH
set /a YNUM=%INPUT_YEAR%  2>nul || goto :INVALID_YEAR

if %MNUM% LSS 1 goto :INVALID_MONTH
if %MNUM% GTR 12 goto :INVALID_MONTH

if %MNUM% LSS 10 (set "MM=0%MNUM%") else (set "MM=%MNUM%")
set "YYYY=%YNUM%"

echo Selected month=%MM% year=%YYYY%>>"%LOGFILE%"
echo Selected month=%MM% year=%YYYY%

REM =========================================================
REM GERAR LISTA DE DIAS
REM =========================================================
set "DAYFILE=%~dp0_days_list.tmp"
if exist "%DAYFILE%" del /f /q "%DAYFILE%"

if not "%SINGLE_DAY%"=="" (
  echo %SINGLE_DAY%>"%DAYFILE%"
) else (
  powershell -NoProfile -Command ^
    "$s=Get-Date -Year %YYYY% -Month %MNUM% -Day 1; $e=$s.AddMonths(1).AddDays(-1); for($d=0;$d -lt $e.Day;$d++){ $s.AddDays($d).ToString('yyyy-MM-dd') }" ^
    > "%DAYFILE%"
)

REM =========================================================
REM LOOP POR DIA
REM =========================================================
for /f "usebackq delims=" %%D in ("%DAYFILE%") do (
  set "CUR_DAY=%%D"

  REM ===== AJUSTE DE FUSO (UTC-3 → UTC) =====
  for /f "delims=" %%I in ('
    powershell -NoProfile ^
    "$from = Get-Date ('%%D 00:00:00'); $from = $from.AddHours(3); $from.ToString('yyyy-MM-dd HH:mm:ss')"
  ') do set "FROM=%%~I"

  for /f "delims=" %%I in ('
    powershell -NoProfile ^
    "$to = Get-Date ('%%D 23:59:59'); $to = $to.AddHours(3); $to.ToString('yyyy-MM-dd HH:mm:ss')"
  ') do set "TO=%%~I"

  echo FROM=!FROM!
  echo TO=!TO!

  set "DAY_FOLDER=reports_!CUR_DAY!"
  if not exist "!DAY_FOLDER!" mkdir "!DAY_FOLDER!"

  for %%T in (%TEMPLATES%) do (
    call :RUN_TEMPLATE %%T "!CUR_DAY!" "!FROM!" "!TO!" "!DAY_FOLDER!"
  )

  powershell -NoProfile -Command ^
    "if(Test-Path '!DAY_FOLDER!'){Remove-Item '!DAY_FOLDER!.zip' -EA SilentlyContinue; Compress-Archive '!DAY_FOLDER!\*' '!DAY_FOLDER!.zip'}" ^
    >>"%LOGFILE%" 2>&1

  if "!KEEP_FOLDER!"=="0" rmdir /s /q "!DAY_FOLDER!"

  echo END DAY !CUR_DAY! %DATE% %TIME%>>"%LOGFILE%"
)

del /f /q "%DAYFILE%"
echo ==== FINISH (Selected Month) %DATE% %TIME% ====>>"%LOGFILE%"
exit /b 0

REM =========================================================
REM FUNÇÃO: EXECUTAR TEMPLATE
REM =========================================================
:RUN_TEMPLATE
set "TPL=%~1"
set "DAYSTR=%~2"
set "FROM_ARG=%~3"
set "TO_ARG=%~4"
set "DAY_FOLDER=%~5"

set "REPORT_NAME=Relatorio_Wialon_%TPL%_%DAYSTR%"
set "OUTPUT_FILE=%DAY_FOLDER%\%REPORT_NAME%.xlsx"

echo [REPORT-START]>>"%LOGFILE%"
echo TemplateID=%TPL%>>"%LOGFILE%"
echo ReportName=%REPORT_NAME%>>"%LOGFILE%"
echo ResourceID=%RESOURCE%>>"%LOGFILE%"
echo ObjectID=%OBJECT%>>"%LOGFILE%"
echo From=%FROM_ARG%>>"%LOGFILE%"
echo To=%TO_ARG%>>"%LOGFILE%"
echo Output=%OUTPUT_FILE%>>"%LOGFILE%"
echo StartTime=%DATE% %TIME%>>"%LOGFILE%"

py "%PY_SCRIPT%" ^
  --token "%TOKEN%" ^
  --resource-id %RESOURCE% ^
  --template-id %TPL% ^
  --object-id %OBJECT% ^
  --from "%FROM_ARG%" --to "%TO_ARG%" ^
  --format xlsx --output "%DAY_FOLDER%\%REPORT_NAME%" ^
  --mysql-host "%MYSQL_HOST%" ^
  --mysql-user "%MYSQL_USER%" ^
  --mysql-pass "%MYSQL_PASS%" ^
  --mysql-db "%MYSQL_DB%" ^
  --timeout 3600 --http-timeout 1200 --verbose ^
  >>"%LOGFILE%" 2>&1

set "RC=!ERRORLEVEL!"
echo ExitCode=!RC!>>"%LOGFILE%"
echo EndTime=%DATE% %TIME%>>"%LOGFILE%"
echo [REPORT-END]>>"%LOGFILE%"
echo.>>"%LOGFILE%"

goto :eof

REM =========================================================
REM ERROS
REM =========================================================
:INVALID_MONTH
echo ERRO: Mes invalido>>"%LOGFILE%"
exit /b 1

:INVALID_YEAR
echo ERRO: Ano invalido>>"%LOGFILE%"
exit /b 1
