@echo off
rem One-click VR launcher for Police 24/7 on a Steam Frame (or any SteamVR headset).
rem
rem   1. starts SteamVR if it is not running, and waits for it
rem   2. launches the "Police 24-7 (VR)" Steam shortcut (added by vr\add_steam_shortcut.py)
rem      -> Play-Police247.ps1 -Vr: PCSX2 windowed with PINE + the frame_bridge
rem
rem Launching through Steam (not PCSX2 directly) is what puts the game on SteamVR's
rem Theater screen with the dashboard closed, so the controller buttons reach the bridge.
rem Steam game id = (shortcut appid 4111256887 << 32) | 0x02000000.
setlocal
set GAMEID=17657713875153321984

tasklist /FI "IMAGENAME eq steam.exe" /NH | find /I "steam.exe" >nul || (
    echo Steam is not running - starting it...
    start "" steam://open/main
    timeout /t 10 /nobreak >nul
)

tasklist /FI "IMAGENAME eq vrserver.exe" /NH | find /I "vrserver.exe" >nul && goto vr_up
echo Starting SteamVR - put the Frame on / connect it to this PC...
start "" steam://rungameid/250820
set /a TRIES=0
:wait_vr
timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq vrserver.exe" /NH | find /I "vrserver.exe" >nul && goto vr_settle
set /a TRIES+=1
if %TRIES% lss 60 goto wait_vr
echo SteamVR did not start within 2 minutes. Start it by hand, then run this again.
pause
exit /b 1
:vr_settle
rem give SteamVR's compositor a moment before a game asks for the Theater screen
timeout /t 8 /nobreak >nul
:vr_up

echo Launching Police 24-7 (VR) through Steam...
start "" steam://rungameid/%GAMEID%
echo.
echo In the headset: close the SteamVR dashboard (system button) once the game shows.
echo Right trigger = fire, point = aim, lean/crouch = cover, hold right grip 1.5 s = recenter.
echo Bridge log: %~dp0vr\bridge.log
timeout /t 10 >nul
