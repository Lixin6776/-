@echo off
chcp 65001 >nul
title Install dependencies
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
echo Press any key to close
pause >nul
