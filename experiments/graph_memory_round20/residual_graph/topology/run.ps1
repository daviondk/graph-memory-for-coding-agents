$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$p=Split-Path -Parent $s
$gpu='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
while (!(Test-Path "$p/forecast-seal.json")){
    if (!(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object {$_.CommandLine -match 'run_fit.ps1'})){throw 'Primary rank stopped before seal'}
    Start-Sleep -Seconds 5
}
& $gpu -B -u "$s/intervene.py" rank
if ($LASTEXITCODE){throw 'Inference intervention failed'}
& $gpu -B -u "$s/intervene.py" score
if ($LASTEXITCODE){throw 'Topology scoring failed'}

