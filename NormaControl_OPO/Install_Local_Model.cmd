@echo off
chcp 65001 >nul
where ollama >nul 2>nul
if errorlevel 1 (
  echo Сначала установите Ollama: https://ollama.com/download
  pause
  exit /b 1
)
echo Загружается локальная модель qwen2.5:14b. На этом шаге нужен интернет.
ollama pull qwen2.5:14b
if errorlevel 1 (
  echo Загрузка не завершена. Проверьте запуск Ollama и подключение к интернету.
  pause
  exit /b 1
)
echo Модель загружена. Инструкция автономного запуска: LOCAL_AI_RU.md
pause
