param([switch]$SkipNode)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolEnv = Join-Path $projectRoot '.local\tools'
$uvExe = Join-Path $toolEnv 'Scripts\uv.exe'
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $uvExe)) {
        & py -3.12 -m venv $toolEnv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Install it or select an existing 3.12 runtime.' }
        & (Join-Path $toolEnv 'Scripts\python.exe') -m pip install 'uv==0.12.19'
        if ($LASTEXITCODE -ne 0) { throw 'Unable to install the local dependency manager.' }
    }
    & $uvExe sync --locked --python 3.12 --no-python-downloads --link-mode=copy
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    if (-not $SkipNode) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Node dependency installation failed.' }
    }
    Write-Output 'Project dependencies are ready. No models or paid services were installed.'
} finally {
    Pop-Location
}
