$ErrorActionPreference='Stop'
$work=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$canonical=Join-Path $work 'graph_memory_round22/native_multiseed/official580/five-seed-results.json'
if (!(Test-Path -LiteralPath $canonical)) {Write-Output 'Canonical evaluation still running';exit 2}
$sealed=Join-Path $PSScriptRoot 'gpu-forecast-seal.json'
$forecast=Join-Path $PSScriptRoot 'gpu-qwen-reference.json'
if ((Test-Path -LiteralPath $sealed) -and (Test-Path -LiteralPath $forecast)) {
    $record=Get-Content -LiteralPath $sealed -Raw | ConvertFrom-Json
    if ((Get-FileHash -LiteralPath $forecast -Algorithm SHA256).Hash.ToLowerInvariant() -eq $record.reference) {
        Write-Output 'Existing complete GPU forecasts match their seal'
        exit 0
    }
}
$mutex=[Threading.Mutex]::new($false,'Local\CodexResearchGraphMemoryFiveSeed')
$owned=$false
try {
    try {$owned=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$owned=$true}
    if (!$owned) {Write-Output 'Shared GPU resource in use';exit 2}
    $env:R39_GPU_LEASE='1'
    $env:LLAMA_ARG_LOG_VERBOSITY='5'
    & 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe' -B -u (Join-Path $PSScriptRoot 'gpu_reference.py')
    if ($LASTEXITCODE -ne 0) {
        $log='D:/CodexResearch/x20-r39-embedding-runtime/runs-r39-gpu-v1/server.log'
        if ((Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash.ToLowerInvariant() -ne '2c79ac22873aa21a0ee6d2e97339b2dad33aec19062f880d221b507e64be0b66') {throw 'Backend verification failed for current GPU run; historical telemetry cannot be reused.'}
        & 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe' -B -u (Join-Path $PSScriptRoot 'seal_gpu.py')
        if ($LASTEXITCODE -ne 0) {throw 'GPU run incomplete or per-state receipts failed verification'}
    }
} finally {
    if ($owned) {$mutex.ReleaseMutex()}
    $mutex.Dispose()
}
