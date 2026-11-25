$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$gpuPy='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
while (!(Test-Path "$s/hash64/results.json")){
    if (!(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object {$_.CommandLine -match 'cpu_fallback[/\\]run.ps1'})){throw 'Main CPU panels stopped before score'}
    Start-Sleep -Seconds 6
}
& $gpuPy -B -u "$s/topology_hash.py" rank
if($LASTEXITCODE){throw 'Hash topology forecasts failed'}
& $gpuPy -B -u "$s/topology_hash.py" score
if($LASTEXITCODE){throw 'Hash topology scoring failed'}
& $cpu -B -u "$s/finish_panel.py" hash64
if($LASTEXITCODE){throw 'Independent verification or panel packaging failed'}

