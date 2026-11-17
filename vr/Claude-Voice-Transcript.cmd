@echo off
rem Open the Claude Voice conversation (the headless Opus session the headset talks to)
rem as a forked copy in a normal Claude Code terminal (full history; typing there does not
rem change what the headset continues).
title Claude Voice transcript
cd /d "%~dp0.."
if not exist "%~dp0claude_voice.session" (echo No voice session yet. & pause & exit /b 1)
set /p SID=<"%~dp0claude_voice.session"
claude --resume %SID% --fork-session
