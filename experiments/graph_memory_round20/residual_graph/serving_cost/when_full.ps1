param([Parameter(Mandatory=$true)][int]$FullExtension)
$ErrorActionPreference='Stop'
$rg=Split-Path -Parent $PSScriptRoot
$hf='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$until=(Get-Date).AddHours(10)
while(Get-Process -Id $FullExtension -ErrorAction SilentlyContinue){
    if((Get-Date) -gt $until){throw 'Canonical extension has exceeded its operating window'}
    Start-Sleep -Seconds 15
}
if(!(Test-Path "$rg/adjacency_control/full/matched-comparisons.json") -or !(Test-Path "$rg/official_modes/no_next_full-results.json")){throw 'Canonical extension is incomplete; retry the appropriate failed stage'}
& $hf -B -u "$PSScriptRoot/bench.py" full
if($LASTEXITCODE){throw 'Full online timing failed'}
& $cpu -B "$PSScriptRoot/report.py"
if($LASTEXITCODE){throw 'Full online timing verification failed'}
& $cpu -B "$rg/report.py"
if($LASTEXITCODE){throw 'Final native report failed'}
& $cpu -B "$rg/seal.py"
if($LASTEXITCODE){throw 'Final native manifest failed'}
& $cpu -B "$rg/verify.py"
if($LASTEXITCODE){throw 'Final native verification failed'}
