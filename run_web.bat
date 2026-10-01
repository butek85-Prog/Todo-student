@echo off
chcp 65001 > nul
title Запуск веб-страницы Планировщика задач
cd /d "%~dp0"

echo ========================================================
echo   Запуск веб-страницы Планировщика задач (Web Todo)
echo ========================================================
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" web_app.py
) else (
    python web_app.py
)

pause
