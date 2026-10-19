@echo off
rem Abre la app en modo desarrollo (datos en %APPDATA%\Arbitros)
cd /d "%~dp0"
set PYTHONPATH=src
".venv\Scripts\python.exe" -m arbitros
