param([Parameter(Mandatory=$true)][int]$PanelProcess)
$ErrorActionPreference='Stop'
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$rg=Split-Path -Parent $PSScriptRoot
$series=Split-Path -Parent $rg
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONUTF8='1'
function Wait-Artifact([string]$Artifact) {
    $until=(Get-Date).AddHours(6)
    while (!(Test-Path -LiteralPath $Artifact)) {
        if (!(Get-Process -Id $PanelProcess -ErrorAction SilentlyContinue) -or ((Get-Date) -gt $until)) { throw "Native hash64 producer has stopped or exceeded its operating window before $Artifact" }
        Start-Sleep -Seconds 6
    }
}
Wait-Artifact "$PSScriptRoot/hash64/forecast-seal.json"
if (!(Test-Path "$series/graph_trigger/hash64-source-transfer.json")) {
    & "$series/graph_trigger/run_cpu.ps1" -Panel hash64
    if ($LASTEXITCODE){throw 'graph_trigger failed'}
}
if (!(Test-Path "$series/union_read/hash64-clean-sensitivity.json")) {
    & "$series/union_read/run_cpu.ps1" -Panel hash64
    if ($LASTEXITCODE){throw 'union_read failed'}
}
Wait-Artifact "$PSScriptRoot/hash64/MANIFEST_SHA256.json"
& $cpu -B "$rg/evidence_flow/analyze.py" score hash64
if ($LASTEXITCODE){throw 'multi-event read failed'}
& $cpu -B "$rg/evidence_flow/report.py"
if ($LASTEXITCODE){throw 'multi-event report failed'}
& $cpu -B "$PSScriptRoot/seal_bundle.py"
if ($LASTEXITCODE){throw 'CPU bundle seal failed'}
& $cpu -B "$PSScriptRoot/verify_bundle.py"
if ($LASTEXITCODE){throw 'CPU bundle verification failed'}
