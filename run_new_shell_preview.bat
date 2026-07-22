@echo off
REM Safe interactive preview of the new NGR Pit Crew shell (sample data only).
REM No telemetry, no UDP port, no config/DB writes. Safe to run anytime.
cd /d "%~dp0"
python preview_new_shell.py
pause
