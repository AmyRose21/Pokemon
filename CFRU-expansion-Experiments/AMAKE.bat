@echo off
rem Ejecuta "python scripts/make.py" desde la carpeta donde este este .bat
rem Si "python" no esta en el PATH, lo busca con el launcher "py" y lo arregla
cd /d "%~dp0"

rem Probar si "python" funciona de verdad
python -c "print(1)" >nul 2>nul
if not errorlevel 1 goto compilar

rem "python" no esta en el PATH. Buscar el real con el launcher "py"
py -3 -c "import sys,os;print(os.path.dirname(sys.executable))" >"%TEMP%\pydir.txt" 2>nul
if errorlevel 1 goto sin_python
set /p PYDIR=<"%TEMP%\pydir.txt"
if not defined PYDIR goto sin_python
set "PATH=%PYDIR%;%PATH%"
echo [AVISO] "python" no estaba en el PATH; se arreglo solo para esta ventana.

:compilar
python scripts/make.py
pause
exit /b

:sin_python
echo.
echo [ERROR] Python no esta instalado o no esta en el PATH.
echo La guia oficial pide Python 3.7.6 descargado de python.org,
echo marcando la casilla "Add Python to PATH" al instalar.
echo.
pause
exit /b
