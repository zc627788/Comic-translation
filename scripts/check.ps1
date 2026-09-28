$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/setup.ps1 first.' }
Push-Location $projectRoot
try {
    & npm.cmd run check
    if ($LASTEXITCODE -ne 0) { throw 'Documentation or extension checks failed.' }
    & npm.cmd run test:fixtures
    if ($LASTEXITCODE -ne 0) { throw 'Fixture boundary checks failed.' }
    & $pythonExe -m ruff check services tests/backend
    if ($LASTEXITCODE -ne 0) { throw 'Python source checks failed.' }
    & $pythonExe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'API boundary tests failed.' }
    & $pythonExe -m services.worker
    if ($LASTEXITCODE -ne 0) { throw 'Worker diagnostics failed.' }
    & (Join-Path $PSScriptRoot 'smoke.ps1')
    Write-Output 'Foundation checks passed. Real model and browser-extension acceptance remain pending.'
} finally {
    Pop-Location
}
