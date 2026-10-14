@echo off
chcp 65001 >nul
title Live Ops Assistant
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
echo.
echo (background services keep running; press any key to close this window)
pause >nul
