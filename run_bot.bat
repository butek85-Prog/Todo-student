@echo off
chcp 65001 > nul
title Telegram Todo Bot
echo ======================================================
echo    Запуск Telegram-бота планировщика задач...
echo ======================================================
echo.
python bot.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ошибка при работе бота. Нажмите любую клавишу для выхода...
    pause > nul
)
