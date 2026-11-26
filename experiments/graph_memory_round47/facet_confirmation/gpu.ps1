$ErrorActionPreference='Stop'
$mutex=[Threading.Mutex]::new($false,'Local\CodexResearchGraphMemoryFiveSeed')
$held=$false
try {
    try {$held=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$held=$true}
    if (!$held) {Write-Output 'Existing GPU lease';exit 2}
    $env:R47_CONFIRM_LEASE='1'
    $env:OPENBLAS_NUM_THREADS='1'
    $env:OMP_NUM_THREADS='1'
    & 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe' -B -u (Join-Path $PSScriptRoot 'predict_gpu.py')
    exit $LASTEXITCODE
} finally {
    if ($held) {$mutex.ReleaseMutex()}
    $mutex.Dispose()
}
