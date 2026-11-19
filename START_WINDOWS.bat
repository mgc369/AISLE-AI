@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0" || exit /b 1
echo.
echo   AISLE.AI - WAREHOUSE INTELLIGENCE LAB
echo   Open the address printed by the server.
echo   Keep this window open while using the app.
echo.

py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    py -3 run.py %*
    goto :server_finished
)

python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 (
    echo Python 3.10 or newer is required. Download from python.org.
    pause
    exit /b 1
)
python run.py %*

:server_finished
set "AISLE_EXIT_CODE=%ERRORLEVEL%"
if not "%AISLE_EXIT_CODE%"=="0" (
    echo.
    echo The server exited with code %AISLE_EXIT_CODE%. See the error above.
    pause
)
exit /b %AISLE_EXIT_CODE%
