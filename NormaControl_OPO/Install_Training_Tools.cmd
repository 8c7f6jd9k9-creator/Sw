@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Устанавливаются дополнительные библиотеки обучения (около 3-4 ГБ). Нужен интернет.
echo PyTorch ставится в сборке с CUDA 12.8 для видеокарт NVIDIA: обычный пакет PyPI для Windows не поддерживает GPU.
"%~dp0runtime\python.exe" -I -X utf8 -m ensurepip
if errorlevel 1 goto fail
"%~dp0runtime\python.exe" -I -X utf8 -m pip install --upgrade "torch>=2.7,<3" --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto fail
"%~dp0runtime\python.exe" -I -X utf8 -m pip install -r "%~dp0requirements-training.txt"
if errorlevel 1 goto fail
"%~dp0runtime\python.exe" -I -X utf8 -c "import torch;print('torch',torch.__version__,'CUDA',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
echo Готово. Проверьте диагностику на вкладке «Обучение ИИ»: должно быть CUDA = True.
echo Базовую модель Hugging Face нужно загрузить отдельно. Веса в комплект не входят.
pause
exit /b 0
:fail
echo Установка не завершена. Проверьте сообщения выше.
pause
exit /b 1
