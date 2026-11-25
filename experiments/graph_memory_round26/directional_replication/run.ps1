param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$env:CUDA_VISIBLE_DEVICES='-1'
$env:TOKENIZERS_PARALLELISM='false'
$env:OPENBLAS_NUM_THREADS='1'
function Run([string]$name,[string[]]$arglist){
    & $Python -B -u (Join-Path $PSScriptRoot $name) @arglist
    if($LASTEXITCODE){throw "Failed $name"}
}
Run 'rep_io.py' @()
Run 'cohort.py' @()
Run 'collect.py' @('choices')
Run 'collect.py' @('read')
Run 'evaluate.py' @()
Run 'strong.py' @()
Run 'verify_replication.py' @()
