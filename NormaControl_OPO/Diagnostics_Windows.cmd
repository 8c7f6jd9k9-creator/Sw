@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0runtime\python.exe" -I "%~dp0app_entry.py" --self-test
if errorlevel 1 (echo Ошибка: смотрите журнал в LOCALAPPDATA\NormaControlOPO\logs.) else (echo Проверка завершена. Файл Windows_self_test.json находится рядом с приложением.)
pause
