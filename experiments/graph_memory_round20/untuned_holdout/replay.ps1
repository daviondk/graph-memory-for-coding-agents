param(
    [ValidateSet('all','available')][string]$Cohorts='all',
    [string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe',
    [switch]$WaitForEncoder
)
$ErrorActionPreference='Stop'
$holdout=$PSScriptRoot
$round=Split-Path $holdout -Parent
$typed=Join-Path $round 'typed_reader/holdout80'
$factor=Join-Path $round 'factor_reader'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
function Invoke-Step([string]$Script,[string[]]$Params){
    & $Python -B -u $Script @Params
    if($LASTEXITCODE){throw "$Script $Params exited $LASTEXITCODE"}
}
$encoderCheck=Join-Path $holdout 'encoder-check.json'
if($WaitForEncoder){while(!(Test-Path -LiteralPath $encoderCheck)){Start-Sleep -Seconds 10}}
if(!(Test-Path -LiteralPath $encoderCheck)){Invoke-Step (Join-Path $holdout 'holdout.py') @('encode')}
if(!(Test-Path -LiteralPath (Join-Path $holdout 'forecast-seal.json'))){Invoke-Step (Join-Path $holdout 'holdout.py') @('predict')}
$rank=Join-Path $holdout 'dense-ranks-extra80.json.gz'
$sha=(Get-FileHash -LiteralPath $rank -Algorithm SHA256).Hash.ToLowerInvariant()
$seal=Get-Content -LiteralPath (Join-Path $holdout 'forecast-seal.json') -Raw | ConvertFrom-Json
if($sha -ne $seal.ranks){throw 'Dense rank identity mismatch'}
if(!(Test-Path -LiteralPath (Join-Path $typed 'forecast-seal.json'))){Invoke-Step (Join-Path $typed 'heldout.py') @('infer',$rank,$sha)}
$ready=@('availability')
if($Cohorts -eq 'all'){
    while(!(Test-Path -LiteralPath (Join-Path $factor 'hash64-weights.json'))){Start-Sleep -Seconds 10}
    $ready+='hash64'
}
foreach($c in $ready){
    if(!(Test-Path -LiteralPath (Join-Path $factor "$c-extra-seal.json"))){Invoke-Step (Join-Path $factor 'external.py') @('predict',$c)}
}
if(!(Test-Path -LiteralPath (Join-Path $holdout 'results.json'))){Invoke-Step (Join-Path $holdout 'holdout.py') @('score')}
if(!(Test-Path -LiteralPath (Join-Path $typed 'results.json'))){Invoke-Step (Join-Path $typed 'heldout.py') @('score',$rank,$sha)}
foreach($c in $ready){
    if(!(Test-Path -LiteralPath (Join-Path $factor "$c-extra-results.json"))){Invoke-Step (Join-Path $factor 'external.py') @('score',$c)}
}
Invoke-Step (Join-Path $holdout 'validate_transfer.py') @()
Invoke-Step (Join-Path $factor 'report.py') @()

Invoke-Step (Join-Path $holdout 'stratified.py') @('test','extra80')
