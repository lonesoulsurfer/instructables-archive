@echo off
title Instructables Archive - One-Click Setup
color 0A
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed or not on PATH.
    echo Download it from https://python.org and try again.
    echo IMPORTANT: tick "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

python run.py
pause
