@echo off
chcp 65001 > nul
title Uvicorn Server (FastAPI + Telegram Bot)
cd /d "%~dp0"

echo ========================================================
echo   Запуск сервера Uvicorn (FastAPI + Telegram Bot)
echo   Адрес: http://localhost:8000
echo ========================================================
echo.

if exist ".venv\Scripts\uvicorn.exe" (
    ".venv\Scripts\uvicorn.exe" main:app --host 0.0.0.0 --port 8000 --reload
) else (
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
)

pause
