$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$r='D:/CodexResearch/x20-isetrace-residual'
$py='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
while(@(Get-ChildItem "$r/graphs-*.json").Count -lt 8){
    if(!(Get-CimInstance Win32_Process -Filter "Name='python.exe'"|Where-Object {$_.CommandLine -match 'residual_graph[/\\]setup_graph.py'})){throw 'Projector stopped before eight shards'}
    Start-Sleep -Seconds 5
}
& $cpu -B -u "$s/vectors.py" prepare
if($LASTEXITCODE){throw 'inventory failed'}
foreach($mode in @('dev','ft','base')){
    & $py -B -u "$s/vectors.py" $mode
    if($LASTEXITCODE){throw "encoder failed at $mode"}
}
