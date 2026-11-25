$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$gpuPython='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
& $cpu -B -u "$s/cache_audit.py" sources
if($LASTEXITCODE){throw 'Copied source vectors failed audit'}
while (!(Test-Path "$s/cost-base.json")){
    if (!(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object {$_.CommandLine -match 'run_vectors.ps1'})){throw 'Encoders stopped early'}
    Start-Sleep -Seconds 10
}
& $gpuPython -B -u "$s/cache_audit.py" direct
if($LASTEXITCODE){throw 'CPU direct audit failed'}

