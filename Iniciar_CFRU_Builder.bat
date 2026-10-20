@echo off
title CFRU Builder - Lanzador
cd /d "%~dp0"

rem Intenta primero con pythonw (GUI sin ventana de consola)
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0cfru_builder.py"
    exit /b
)

rem Si no hay pythonw, usa python con consola visible (utl para ver errores)
where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0cfru_builder.py"
    goto :fin
)

rem Ultimo intento: lanzador 'py' de Windows
py -3 "%~dp0cfru_builder.py"

:fin
echo.
pause
