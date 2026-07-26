@echo off
REM Start the QuMail KM simulator (ETSI 014) on http://127.0.0.1:8100
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
echo [QuMail] KM simulator -> http://127.0.0.1:8100
"%PY%" -m km_simulator.main
