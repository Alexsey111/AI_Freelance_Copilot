@echo off
rem Ядро на отдельной базе прогона и реальном провайдере.
rem Запуск: двойной щелчок по файлу или из PowerShell:  .\scripts\run_live.cmd
rem Ключ берётся из .env (LLM_API_KEY) — в командной строке он не появляется.
setlocal
cd /d "%~dp0.."

set DATABASE_URL=sqlite:///./data/live.db
set LLM_PROVIDER=openai

echo.
echo   База:     %DATABASE_URL%
echo   Провайдер: %LLM_PROVIDER%  (реальная модель, тратит деньги)
echo   Адрес:    http://127.0.0.1:8800
echo.
echo   Остановить: Ctrl+C в этом окне.
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8800
endlocal
