$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    & .venv/Scripts/python.exe -m scripts.make-korean-fixture
    if ($LASTEXITCODE -ne 0) { throw 'Run setup.ps1 first; local Windows fonts are required.' }
    & .venv/Scripts/python.exe -m uvicorn services.api.lab:app --host 127.0.0.1 --port 4176 --no-access-log
} finally { Pop-Location }
