@echo off
rem Police 911 (arcade, ver UAD) in MAME with emulated body sensor.
rem See arcade-re\ARCADE_FINDINGS.md. Keys: F2 = Test/Service, 5 = coin,
rem 1 = start, mouse = gun (left button = trigger), Esc = quit.
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%MAME\mame0289"
mame.exe p911ud -skip_gameinfo -mouse -lightgun_device mouse -autoboot_script "%ROOT%arcade-re\mame\p911_sensor.lua" %*
endlocal
