@echo off
REM Start the QuMail backend API on http://127.0.0.1:8000
REM Requires a .env file (copy .env.example -> .env and set KEYSTORE_MASTER_PASSWORD).
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"
if not exist ".env" (
  echo [QuMail] ERROR: .env not found. Copy .env.example to .env and set KEYSTORE_MASTER_PASSWORD.
  exit /b 1
)
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
echo [QuMail] backend API -> http://127.0.0.1:8000
"%PY%" -m backend.main
