param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$env:CUDA_VISIBLE_DEVICES='-1'
$env:OPENBLAS_NUM_THREADS='1'
$env:TOKENIZERS_PARALLELISM='false'
function Job-Step([string]$Name,[string[]]$Argv){
    & $Python -B -u (Join-Path $PSScriptRoot $Name) @Argv
    if($LASTEXITCODE){throw "Failed $Name $Argv"}
}
Job-Step 'freeze.py' @()
foreach($ds in 'ise','mdd','squad'){
    if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot "$ds-choice-seal.json"))){Job-Step 'dataset.py' @('select',$ds)}
    if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot "$ds-open-seal.json"))){Job-Step 'dataset.py' @('run',$ds)}
    if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot "$ds-results.json"))){Job-Step 'analyse.py' @($ds)}
    if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot "$ds-secondary.json"))){Job-Step 'secondary.py' @($ds)}
    Job-Step 'audit25.py' @($ds)
}
