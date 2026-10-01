@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Устанавливаются дополнительные библиотеки обучения (около 3-4 ГБ). Нужен интернет.
echo PyTorch ставится в сборке с CUDA для видеокарт NVIDIA: обычный пакет PyPI для Windows работает только на CPU.
rem pip загружается с PyPI с проверкой SHA-256 (колесо pip не входит в архив).
"%~dp0runtime\python.exe" -I -X utf8 "%~dp0tools\bootstrap_pip.py"
if errorlevel 1 goto fail
rem Сначала новейшая сборка CUDA 13.0, затем 12.8 и 12.6.
echo Попытка: PyTorch cu130
"%~dp0runtime\python.exe" -I -X utf8 -m pip install --upgrade "torch>=2.7,<3" --index-url https://download.pytorch.org/whl/cu130
if not errorlevel 1 goto torch_ok
echo Попытка: PyTorch cu128
"%~dp0runtime\python.exe" -I -X utf8 -m pip install --upgrade "torch>=2.7,<3" --index-url https://download.pytorch.org/whl/cu128
if not errorlevel 1 goto torch_ok
echo Попытка: PyTorch cu126
"%~dp0runtime\python.exe" -I -X utf8 -m pip install --upgrade "torch>=2.7,<3" --index-url https://download.pytorch.org/whl/cu126
if not errorlevel 1 goto torch_ok
goto fail
:torch_ok
"%~dp0runtime\python.exe" -I -X utf8 -m pip install -r "%~dp0requirements-training.txt"
if errorlevel 1 goto fail
"%~dp0runtime\python.exe" -I -X utf8 -c "import torch;print('torch',torch.__version__,'CUDA',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
echo Готово. Проверка конвейера: runtime\python.exe -I -X utf8 tools\lora_pipeline_check.py
echo Базовую модель Hugging Face нужно загрузить отдельно. Веса в комплект не входят.
pause
exit /b 0
:fail
echo Установка не завершена. Проверьте сообщения выше.
pause
exit /b 1
