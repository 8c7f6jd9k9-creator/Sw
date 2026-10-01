@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0..\NormaControl_OPO\runtime\python.exe"
if not exist "%PY%" set /p APP=Укажите папку программы НормаКонтроль ОПО, где лежит NormaControl.exe: 
if not exist "%PY%" set "PY=%APP%\runtime\python.exe"
if not exist "%PY%" goto noruntime
"%PY%" -I -X utf8 "%~dp0license_tool.py" drives
pause
exit /b 0
:noruntime
echo Не найден runtime\python.exe. Распакуйте программу НормаКонтроль ОПО и укажите её папку.
pause
exit /b 1
