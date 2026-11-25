param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$here=$PSScriptRoot
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:CUDA_VISIBLE_DEVICES='-1'
foreach($step in @(@('build','build.json'),@('static','static-times.json.gz'),@('dynamic','dynamic-complete.json'),@('durability','durable-cached-repair.json'))){
    if(Test-Path -LiteralPath (Join-Path $here $step[1])){continue}
    & $Python -B -u (Join-Path $here 'bench.py') $step[0]
    if($LASTEXITCODE){throw "Failed physical step $($step[0])"}
}

