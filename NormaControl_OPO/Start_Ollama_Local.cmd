@echo off
chcp 65001 >nul
set OLLAMA_NO_CLOUD=1
set OLLAMA_HOST=127.0.0.1:11434
where ollama >nul 2>nul
if errorlevel 1 (
  echo Установите Ollama с https://ollama.com/download
  pause
  exit /b 1
)
echo Закройте ранее запущенный Ollama, чтобы этот сервер работал без облачных функций.
echo Оставьте это окно открытым и запустите Start_Windows.cmd в другом окне.
ollama serve
pause
