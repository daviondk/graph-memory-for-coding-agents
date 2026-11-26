$ErrorActionPreference='Stop'
$canonical=Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'graph_memory_round22/native_multiseed/official580/five-seed-results.json'
if ($env:R40_WAIT_FOR_CANONICAL -eq '1' -and !(Test-Path -LiteralPath $canonical)) {Write-Output 'Canonical GPU evaluation active';exit 2}
$mutex=[Threading.Mutex]::new($false,'Local\CodexResearchGraphMemoryFiveSeed')
$held=$false
try {
    try {$held=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$held=$true}
    if (!$held) {Write-Output 'GPU lease owned by another experiment';exit 2}
    $env:R40_GPU_LEASE='1'
    & 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe' -B -u (Join-Path $PSScriptRoot 'embed_gpu.py')
    exit $LASTEXITCODE
} finally {
    if ($held) {$mutex.ReleaseMutex()}
    $mutex.Dispose()
}
