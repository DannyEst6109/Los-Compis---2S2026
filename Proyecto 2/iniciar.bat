@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 src\app.py
) else (
    python src\app.py
)

if errorlevel 1 (
    echo.
    echo No fue posible iniciar la aplicacion. Verifique que Python 3 este instalado.
    pause
)
