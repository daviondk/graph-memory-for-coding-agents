param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$env:CUDA_VISIBLE_DEVICES='-1'
$env:TOKENIZERS_PARALLELISM='false'
$env:OPENBLAS_NUM_THREADS='1'
function Execute-Step([string[]]$Argv) {
    & $Python -B -u (Join-Path $PSScriptRoot $Argv[0]) $Argv[1..($Argv.Count-1)]
    if($LASTEXITCODE){throw "Failed $Argv"}
}
& $Python -B (Join-Path $PSScriptRoot 'freeze.py')
if($LASTEXITCODE){throw 'input verification failed'}
foreach($ds in 'ise','mdd'){
    if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot "$ds-choice-seal.json"))){Execute-Step @("$ds.py",'select')}
    if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot "$ds-open-seal.json"))){Execute-Step @("$ds.py",'execute')}
    if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot "$ds-results.json"))){Execute-Step @('evaluate.py',$ds)}
    Execute-Step @('audit.py',$ds)
}
