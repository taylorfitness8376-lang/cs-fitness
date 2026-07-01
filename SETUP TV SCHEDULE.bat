@echo off
:: CS Fitness — Full Setup
:: Run this ONCE as Administrator.
:: Right-click this file and choose "Run as administrator"

cd /d %~dp0
set FOLDER=%~dp0

echo CS Fitness — Setup
echo ==================
echo.

if not exist "%FOLDER%logs" mkdir "%FOLDER%logs"

:: ── Remove any old NSSM service if present ────────────────
if exist "%FOLDER%nssm.exe" (
    "%FOLDER%nssm.exe" stop   CSFitness >nul 2>&1
    "%FOLDER%nssm.exe" remove CSFitness confirm >nul 2>&1
    echo   Removed old NSSM service.
)

:: ── Remove old tasks ──────────────────────────────────────
schtasks /delete /tn "CSFitness_App"    /f >nul 2>&1
schtasks /delete /tn "CSFitness_TV_On"  /f >nul 2>&1
schtasks /delete /tn "CSFitness_TV_Off" /f >nul 2>&1

:: ── App: auto-start at login, hidden, restart on failure ──
echo Installing app auto-start...
schtasks /create /tn "CSFitness_App" ^
  /tr "wscript.exe \"%FOLDER%start_hidden.vbs\"" ^
  /sc onlogon ^
  /delay 0000:20 ^
  /ru "%USERNAME%" ^
  /f
echo   App scheduled to start silently at login (20s delay).

:: Set restart on failure via PowerShell (schtasks can't do this directly)
powershell -Command "$t = Get-ScheduledTask -TaskName 'CSFitness_App'; $s = New-ScheduledTaskSettingsSet -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero); Set-ScheduledTask -TaskName 'CSFitness_App' -Settings $s" >nul 2>&1
echo   Restart on failure configured (retries every 1 minute).

:: ── TV on/off schedule ────────────────────────────────────
echo.
echo Setting up TV schedule...
schtasks /create /tn "CSFitness_TV_On"  /tr "\"%FOLDER%tv_on.bat\""  /sc daily /st 04:00 /ru SYSTEM /f
echo   TV ON  scheduled at 04:00 daily

schtasks /create /tn "CSFitness_TV_Off" /tr "\"%FOLDER%tv_off.bat\"" /sc daily /st 22:00 /ru SYSTEM /f
echo   TV OFF scheduled at 22:00 daily

:: ── Start the app now without waiting for a reboot ────────
echo.
echo Starting app now...
start "" wscript.exe "%FOLDER%start_hidden.vbs"
timeout /t 3 /nobreak >nul
echo   App started in background.

:: ── Done ──────────────────────────────────────────────────
echo.
echo ==================
echo Setup complete.
echo.
echo   App runs silently — no window to accidentally close.
echo   Restarts itself automatically if it ever stops.
echo   Logs saved to: %FOLDER%logs\service.log
echo.
echo   CMS:  http://localhost:9090/cms  (password: csfit2024)
echo ==================
echo.
pause
