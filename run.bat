@echo off
echo ================================================
echo     Prefix Hub - Launcher
echo ================================================

call venv\Scripts\activate
echo.
echo Starting Dashboard (press Ctrl+C to stop)...
uvicorn dashboard.src.main:app --host 0.0.0.0 --port 8000 --reload
