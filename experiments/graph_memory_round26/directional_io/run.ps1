param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$env:TOKENIZERS_PARALLELISM='false'
$env:OPENBLAS_NUM_THREADS='1'
$env:CUDA_VISIBLE_DEVICES='-1'
function Step([string]$name){& $Python -B -u (Join-Path $PSScriptRoot $name);if($LASTEXITCODE){throw "Failed $name"}}
Step 'cfg.py'
Step 'make_db.py'
foreach($p in @(@('bench.py','measurement-seal.json'),@('online.py','online-results.json'),@('matched.py','matched-results.json'))){
    if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot $p[1]))){Step $p[0]}
}
Step 'results.py'
Step 'verify26.py'
