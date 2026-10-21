@echo off
rem Ejecuta "python scripts/make.py" desde la carpeta donde este este .bat
cd /d "%~dp0"
python scripts/make.py
pause
