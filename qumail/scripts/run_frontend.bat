@echo off
REM Start the QuMail frontend (Vite dev server; use electron:dev for the desktop shell).
setlocal
cd /d "%~dp0..\frontend"
if not exist "node_modules" (
  echo [QuMail] Installing frontend dependencies...
  call npm install || exit /b 1
)
echo [QuMail] frontend dev server -> http://127.0.0.1:5173
npm run dev
