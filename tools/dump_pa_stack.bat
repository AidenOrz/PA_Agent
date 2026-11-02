@echo off
rem ============================================================
rem  PA_Agent freeze diagnostic: dump the stack of every python.exe.
rem  Run this WHILE the app window is frozen ("not responding").
rem
rem  Output: logs\stackdump.txt (relative to the repo root).
rem  Tool:   py-spy (https://github.com/benfred/py-spy), installed on
rem          first run if it is missing. On Windows, py-spy usually
rem          needs an elevated shell to inspect another process.
rem
rem  The interpreter running PA_Agent is taken from %PYTHON% when set,
rem  otherwise from PATH. py-spy is a standalone binary -- it is NOT
rem  a python module, so `python -m py-spy` does not exist.
rem ============================================================
setlocal
rem %~dp0 ends with a backslash; %%~fI normalises "tools\.." to the repo root.
for %%I in ("%~dp0..") do set ROOT=%%~fI
set OUT=%ROOT%\logs\stackdump.txt
if not defined PYTHON set PYTHON=python

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

call :resolve_pyspy
if not defined PYSPY (
    echo py-spy not found, installing it once with %PYTHON% ...
    %PYTHON% -m pip install -q py-spy
    call :resolve_pyspy
)
if not defined PYSPY (
    echo.
    echo Could not find or install py-spy. Install it manually:
    echo   %PYTHON% -m pip install py-spy
    goto :end
)

echo Using py-spy: %PYSPY%
echo PA_Agent thread stack dump > "%OUT%"
echo %date% %time% >> "%OUT%"

for /f "tokens=2 delims=," %%P in ('tasklist /fo csv /nh ^| findstr /i "python.exe"') do (
    echo ======== PID %%~P ======== >> "%OUT%"
    "%PYSPY%" dump --pid %%~P --native >> "%OUT%" 2>&1
)

echo.
echo Done. Please send this file for analysis:
echo   %OUT%
goto :end

:resolve_pyspy
set PYSPY=
for /f "delims=" %%I in ('where py-spy 2^>nul') do if not defined PYSPY set PYSPY=%%I
if defined PYSPY goto :eof
for /f "delims=" %%I in ('%PYTHON% -c "import os,sys;print(os.path.dirname(sys.executable))" 2^>nul') do (
    if exist "%%I\Scripts\py-spy.exe" set PYSPY=%%I\Scripts\py-spy.exe
    if exist "%%I\Scripts\py-spy" set PYSPY=%%I\Scripts\py-spy
)
goto :eof

:end
pause
