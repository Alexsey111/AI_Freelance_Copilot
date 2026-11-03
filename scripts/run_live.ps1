# Ядро на отдельной базе прогона и реальном провайдере.
# Запуск из PowerShell:  .\scripts\run_live.ps1
# Если PowerShell блокирует скрипты:
#   powershell -ExecutionPolicy Bypass -File .\scripts\run_live.ps1
# Ключ берётся из .env (LLM_API_KEY) — в командной строке он не появляется.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:DATABASE_URL = "sqlite:///./data/live.db"
$env:LLM_PROVIDER = "openai"

Write-Host ""
Write-Host "  База:      $env:DATABASE_URL"
Write-Host "  Провайдер: $env:LLM_PROVIDER  (реальная модель, тратит деньги)"
Write-Host "  Адрес:     http://127.0.0.1:8800"
Write-Host ""
Write-Host "  Остановить: Ctrl+C в этом окне."
Write-Host ""

& "$root\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8800
