@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"

if not exist "%FRONTEND_DIR%\package.json" (
  echo Frontend folder not found: %FRONTEND_DIR%
  exit /b 1
)

if not exist "%BACKEND_DIR%\app\main.py" (
  echo Backend folder not found: %BACKEND_DIR%
  exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
  echo Frontend dependencies are missing.
  echo Run this first:
  echo   cd /d "%FRONTEND_DIR%" ^&^& npm install
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

echo Starting NokoTracker locally...
echo.
echo Frontend: http://127.0.0.1:5173
echo Backend:  http://127.0.0.1:8000/docs
echo.
echo Note: http://127.0.0.1:8000 is the API backend, so JSON there is normal.
echo.

start "NokoTracker Backend" /D "%BACKEND_DIR%" cmd /k ""%PYTHON_EXE%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
start "NokoTracker Frontend" /D "%FRONTEND_DIR%" cmd /k "npm run dev"
