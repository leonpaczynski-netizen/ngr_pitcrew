@echo off
rem Run the wind reflash wizard from PowerShell or cmd.
rem
rem `bash scripts/wind-reflash.sh` does NOT work from PowerShell on this
rem machine: Windows ships its own bash.exe in System32 that shims to WSL, and
rem with no distro installed it fails with
rem     execvpe(/bin/bash) failed: No such file or directory
rem which reads like the script is missing and is nothing of the kind. This
rem finds Git's bash and hands the script to that instead.
rem
rem Note for anyone editing: %ProgramFiles(x86)% may not appear inside a
rem parenthesised if-block or an echo within one - the ")" in the variable
rem name closes the block early, and cmd reports
rem "\Git\bin\bash.exe was unexpected at this time". It is resolved into a
rem plain variable first, outside any block, for exactly that reason.

setlocal EnableExtensions
set "PF86=%ProgramFiles(x86)%"

set "GITBASH=%ProgramFiles%\Git\bin\bash.exe"
if exist "%GITBASH%" goto :found

set "GITBASH=%PF86%\Git\bin\bash.exe"
if exist "%GITBASH%" goto :found

set "GITBASH=%LOCALAPPDATA%\Programs\Git\bin\bash.exe"
if exist "%GITBASH%" goto :found

echo.
echo   Could not find Git's bash on this machine.
echo   Install Git for Windows, or open a Git Bash window and run:
echo     bash scripts/wind-reflash.sh
echo.
exit /b 1

:found
rem %* passes --restore straight through.
"%GITBASH%" "%~dp0wind-reflash.sh" %*
exit /b %ERRORLEVEL%
