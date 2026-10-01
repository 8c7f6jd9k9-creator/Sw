@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Устанавливаются дополнительные библиотеки обучения. Нужен интернет.
"%~dp0runtime\python.exe" -I -m ensurepip
if errorlevel 1 goto fail
"%~dp0runtime\python.exe" -I -m pip install -r "%~dp0requirements-training.txt"
if errorlevel 1 goto fail
echo Готово. Проверьте диагностику на вкладке обучения и доступность CUDA.
echo Базовую модель Hugging Face нужно загрузить отдельно. Веса в комплект не входят.
pause
exit /b 0
:fail
echo Установка не завершена. Проверьте сообщения выше.
pause
exit /b 1
