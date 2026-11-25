$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
while (!(Test-Path "$s/topology/results.json")){
    if (!(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object {$_.CommandLine -match 'topology[/\\]run.ps1'})){throw 'Secondary run stopped before results'}
    Start-Sleep -Seconds 8
}
& $cpu -B -u "$s/topology/strata.py" run
if ($LASTEXITCODE){throw 'Stratum scores failed'}
& $cpu -B -u "$s/report.py"
if ($LASTEXITCODE){throw 'Report failed'}
& $cpu -B -u "$s/seal.py"
if ($LASTEXITCODE){throw 'Seal failed'}
& $cpu -B -u "$s/verify.py"
if ($LASTEXITCODE){throw 'Independent verification failed'}

