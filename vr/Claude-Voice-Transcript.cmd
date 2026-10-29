@echo off
rem Open the Claude Voice conversation (the headless Opus session the headset talks to)
rem in a normal interactive Claude Code terminal, with its full history.
title Claude Voice transcript
cd /d "%~dp0.."
if not exist "%~dp0claude_voice.session" (echo No voice session yet. & pause & exit /b 1)
set /p SID=<"%~dp0claude_voice.session"
claude --resume %SID%
