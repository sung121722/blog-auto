@echo off
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting admin rights...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

echo Running as Administrator...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0reg_tasks_system.ps1"
echo.
pause
