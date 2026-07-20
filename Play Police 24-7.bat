@echo off
rem Double-click launcher for Police 24/7.
rem Default = authentic camera path (emulated Konami Capture Eye).
rem Double-click shows a checkbox dialog (camera motion + optional iPhone gun).
rem Pass args to skip the dialog, e.g.:  "Play Police 24-7.bat" -Motion bridge
rem                                      "Play Police 24-7.bat" -Phone
if "%~1"=="" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Play-Police247.ps1" -Gui
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Play-Police247.ps1" %*
)
if errorlevel 1 pause
