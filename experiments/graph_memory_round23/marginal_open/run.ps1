param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$dir=$PSScriptRoot
$env:PYTHONUTF8='1'
$env:TOKENIZERS_PARALLELISM='false'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:CUDA_VISIBLE_DEVICES='-1'
foreach($step in @(@('prepare.py','visible-seal.json'),@('select_visible.py','choice-seal.json'),@('execute.py','opened-seal.json'),@('score.py','results.json'),@('cost_control.py','cost-results.json'))){
    if(!(Test-Path -LiteralPath (Join-Path $dir $step[1]))){
        & $Python -B -u (Join-Path $dir $step[0])
        if($LASTEXITCODE){throw "failed $($step[0])"}
    }
}
& $Python -B -u (Join-Path $dir 'verify.py')
if($LASTEXITCODE){throw 'verification failed'}
