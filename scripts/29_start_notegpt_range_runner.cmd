@echo off
setlocal

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

set "PYTHONUNBUFFERED=1"

".\.venv\Scripts\python.exe" -u ".\scripts\27_run_notegpt_batch_range.py" --start-batch %1 %2 %3 %4 %5 %6

endlocal
