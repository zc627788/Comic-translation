param([ValidateRange(1024, 65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/setup.ps1 first.' }
Push-Location $projectRoot
try {
    & $pythonExe -m uvicorn services.api.app:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'API server exited with an error.' }
} finally {
    Pop-Location
}
