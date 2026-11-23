$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$gpu='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONUTF8='1'
$env:RAYON_NUM_THREADS='3'
while (!(Test-Path -LiteralPath "$s/trained-checkpoint.json")) {
    $p=Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {$_.CommandLine -match 'trained_rank[/\\]train.py.+run'}
    if (!$p){throw 'Trainer exited without checkpoint receipt; inspect train.err.'}
    Start-Sleep -Seconds 10
}
foreach($stage in @('lock','embed','predict')){
    $exe=if ($stage -eq 'embed'){$gpu}else{$cpu}
    & $exe -B -u "$s/test_retrieval.py" $stage
    if ($LASTEXITCODE -ne 0){throw "Failed stage $stage"}
}
& $cpu -B -u "$s/score.py"
if ($LASTEXITCODE -ne 0){throw 'Failed native scoring'}
& $cpu -B -u "$s/rank_diagnostics.py"
if ($LASTEXITCODE -ne 0){throw 'Failed table calibration'}
