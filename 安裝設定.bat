@echo off
rem Interactive setup wizard (this one needs a console window on purpose: it asks you questions).
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul && (python -X utf8 setup.py) || (py -3 -X utf8 setup.py)
echo.
pause
