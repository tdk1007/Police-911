@echo off
rem Talk to Claude Code from the headset (claude_voice.py via frame_bridge --voice-only).
rem Launched by the "Claude Voice" Steam / Start menu shortcuts (add_steam_shortcut.py).
title Claude Voice
cd /d "%~dp0"
py -u frame_bridge.py --voice-only %*
if errorlevel 1 pause
