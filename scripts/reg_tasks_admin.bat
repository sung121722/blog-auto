@echo off
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

set WRAPPER=C:\Users\kang_\Downloads\blog-writer_mcp\run_publish.bat

schtasks /delete /tn "BlogAuto_MWF_AM3" /f 2>nul
schtasks /delete /tn "BlogAuto_TTS_AM3" /f 2>nul
schtasks /delete /tn "BlogAuto_MWF_AM9" /f 2>nul
schtasks /delete /tn "BlogAuto_TTS_AM9" /f 2>nul
schtasks /delete /tn "BlogAuto_MWF" /f 2>nul
schtasks /delete /tn "BlogAuto_TTS" /f 2>nul

schtasks /create /tn "BlogAuto_MWF_AM3" /tr "\"%WRAPPER%\"" /sc WEEKLY /d MON,WED,FRI /st 03:00 /rl HIGHEST /f /it
if %errorlevel% equ 0 (echo [OK] MWF 03:00 registered) else (echo [ERROR] MWF 03:00 failed)

schtasks /create /tn "BlogAuto_TTS_AM3" /tr "\"%WRAPPER%\"" /sc WEEKLY /d TUE,THU,SAT /st 03:00 /rl HIGHEST /f /it
if %errorlevel% equ 0 (echo [OK] TTS 03:00 registered) else (echo [ERROR] TTS 03:00 failed)

schtasks /create /tn "BlogAuto_MWF_AM9" /tr "\"%WRAPPER%\"" /sc WEEKLY /d MON,WED,FRI /st 09:00 /rl HIGHEST /f /it
if %errorlevel% equ 0 (echo [OK] MWF 09:00 registered) else (echo [ERROR] MWF 09:00 failed)

schtasks /create /tn "BlogAuto_TTS_AM9" /tr "\"%WRAPPER%\"" /sc WEEKLY /d TUE,THU,SAT /st 09:00 /rl HIGHEST /f /it
if %errorlevel% equ 0 (echo [OK] TTS 09:00 registered) else (echo [ERROR] TTS 09:00 failed)

echo Done.
pause
