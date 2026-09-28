$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/setup.ps1 first.' }
$smokeDirectory = Join-Path $projectRoot '.local\smoke'
New-Item -ItemType Directory -Path $smokeDirectory -Force | Out-Null
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$smokePort = $listener.LocalEndpoint.Port
$listener.Stop()
Add-Type -AssemblyName System.Net.Http
$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(2)
$process = $null
try {
    $process = Start-Process -FilePath $pythonExe -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -ArgumentList @('-m', 'uvicorn', 'services.api.app:app', '--host', '127.0.0.1', '--port', $smokePort) -RedirectStandardOutput (Join-Path $smokeDirectory 'api.out.log') -RedirectStandardError (Join-Path $smokeDirectory 'api.err.log')
    $baseUrl = 'http://127.0.0.1:' + $smokePort
    $started = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($process.HasExited) { throw 'The smoke API process exited before startup.' }
        try {
            $response = $client.GetAsync($baseUrl + '/health/live').GetAwaiter().GetResult()
            $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
            $started = ([int]$response.StatusCode -eq 200 -and $body.service -eq 'comic-translation-api')
            $response.Dispose()
            if ($started) { break }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (-not $started) { throw 'Local API did not become live.' }
    $ready = $client.GetAsync($baseUrl + '/health/ready').GetAwaiter().GetResult()
    $readyBody = $ready.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
    if ([int]$ready.StatusCode -ne 503 -or $readyBody.ready) { throw 'Foundation falsely claims model readiness.' }
    $ready.Dispose()
    $payload = [System.Net.Http.StringContent]::new('{}', [System.Text.Encoding]::UTF8, 'application/json')
    $batch = $client.PostAsync($baseUrl + '/v1/batches', $payload).GetAwaiter().GetResult()
    $batchBody = $batch.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
    if ([int]$batch.StatusCode -ne 503 -or $batchBody.error.code -ne 'MODEL_NOT_READY') { throw 'Foundation unexpectedly accepted a translation task.' }
    $batch.Dispose()
    $payload.Dispose()
    Write-Output 'PASS: real local API startup; live=200, model-ready=503, translation=503; no paid calls.'
} finally {
    $client.Dispose()
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id
        $process.WaitForExit()
    }
}
