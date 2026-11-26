$ErrorActionPreference='Stop'
$lease=[Threading.Mutex]::new($false,'Local\CodexResearchGraphMemoryFiveSeed')
$active=$false
try {
    try {$active=$lease.WaitOne(0)} catch [Threading.AbandonedMutexException] {$active=$true}
    if (!$active) {Write-Output 'GPU mutex owned by another experiment';exit 2}
    $env:R48_CACHE_GPU_LEASE='1'
    $env:OPENBLAS_NUM_THREADS='1'
    $env:OMP_NUM_THREADS='1'
    & 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe' -B -u (Join-Path $PSScriptRoot 'gpu_measure.py')
    exit $LASTEXITCODE
} finally {if ($active) {$lease.ReleaseMutex()};$lease.Dispose()}

