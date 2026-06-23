@echo off
REM Launcher for Windows Task Scheduler: runs one classification pass and logs it.
REM %~dp0 = the folder this .bat lives in, so it works regardless of where it's called from.
cd /d "%~dp0"
python src\poller.py --once >> poller.log 2>&1
