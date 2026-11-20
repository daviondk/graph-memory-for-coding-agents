param(
    [Parameter(Mandatory)][ValidateSet('Start','Status','Stop')][string]$Action,
    [Parameter(Mandatory)][string]$RunDirectory,
    [string]$Interpreter,
    [string]$Checkpoint,
    [string]$ExtraLibraries,
    [int]$Port=18991
)
$ErrorActionPreference = 'Stop'
$run = [IO.Path]::GetFullPath($RunDirectory)
$program = Join-Path $run 'serve.py'
$pidFile = Join-Path $run 'service.pid'

if ($Action -eq 'Start') {
    if (-not $Interpreter -or -not $Checkpoint) { throw 'Start requires Interpreter and Checkpoint' }
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        throw "TCP port $Port already has a listener"
    }
    New-Item -ItemType Directory -Force -Path $run | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'serve.py') -Destination $program
    if ($ExtraLibraries) { $env:PYTHONPATH = $ExtraLibraries }
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $env:OMP_NUM_THREADS = '3'
    $env:OPENBLAS_NUM_THREADS = '1'
    $env:TEMP = $run
    $env:TMP = $run
    $arguments = @('-u', ('"'+$program+'"'), '--model', ('"'+$Checkpoint+'"'),
                   '--runtime', ('"'+$run+'"'), '--max-output', '512', '--port', $Port)
    $started = Start-Process -FilePath $Interpreter -ArgumentList $arguments -WorkingDirectory $run -WindowStyle Hidden -RedirectStandardOutput (Join-Path $run 'stdout.log') -RedirectStandardError (Join-Path $run 'stderr.log') -PassThru
    $started.Id | Set-Content -LiteralPath $pidFile -NoNewline
    Write-Output "Started local model loader PID $($started.Id)"
    return
}
if ($Action -eq 'Status') {
    Invoke-RestMethod "http://127.0.0.1:$Port/health"
    return
}

# This service may have a small Python venv launcher plus the actual listening
# interpreter. Require its recorded owner, staged source and exact loopback listener.
$owner = [int](Get-Content -Raw -LiteralPath $pidFile)
$listener = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
if ($listener.Count -ne 1 -or $listener[0].LocalAddress -ne '127.0.0.1') {
    throw 'Expected one loopback listener'
}
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
if (($process.ProcessId -ne $owner -and $process.ParentProcessId -ne $owner) -or
    $process.Name -ne 'python.exe' -or -not $process.CommandLine.Contains($program)) {
    throw 'PID, runtime path or parent verification failed'
}
$state = Get-Content -Raw -LiteralPath (Join-Path $run 'state.json') | ConvertFrom-Json
$live = Invoke-RestMethod "http://127.0.0.1:$Port/health"
if ($state.instance -ne $live.instance) { throw 'Service instance mismatch' }
Stop-Process -Id $process.ProcessId -Force
Write-Output "Stopped verified model interpreter PID $($process.ProcessId)"
