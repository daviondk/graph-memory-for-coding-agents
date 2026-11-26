$ErrorActionPreference='Stop'
$mutex=[Threading.Mutex]::new($false,'Local\CodexResearchGraphMemoryFiveSeed')
$locked=$false
try {
    try {$locked=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$locked=$true}
    if (!$locked) {Write-Output 'GPU lease held'; exit 2}
    $env:R49_GPU_LEASE='1'
    $env:OPENBLAS_NUM_THREADS='1'
    $env:OMP_NUM_THREADS='1'
    & 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe' -B -u (Join-Path $PSScriptRoot 'run_gpu.py')
    exit $LASTEXITCODE
} finally {if ($locked) {$mutex.ReleaseMutex()};$mutex.Dispose()}

