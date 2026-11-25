param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$holdout=$PSScriptRoot
$round=Split-Path $holdout -Parent
$factor=Join-Path $round 'factor_reader'
$channels=Join-Path $factor 'channel_controls'
function Wait-File([string]$Path){while(!(Test-Path -LiteralPath $Path)){Start-Sleep -Seconds 5}}
function Step([string]$Script,[string[]]$Params){
    & $Python -B -u $Script @Params
    if($LASTEXITCODE){throw "$Script $Params exited $LASTEXITCODE"}
}
Wait-File (Join-Path $holdout 'forecast-seal.json')
if(!(Test-Path -LiteralPath (Join-Path $channels 'extra80-seal.json'))){Step (Join-Path $channels 'channels.py') @('predict','extra80')}
Wait-File (Join-Path $factor 'hash64-extra-outcomes.json.gz')
Wait-File (Join-Path $round 'typed_reader/holdout80/results.json')
if(!(Test-Path -LiteralPath (Join-Path $channels 'extra80-results.json'))){Step (Join-Path $channels 'channels.py') @('score','extra80')}
Step (Join-Path $channels 'channels.py') @('report')
Step (Join-Path $factor 'native_metrics.py') @('extra80')
Step (Join-Path $holdout 'stratified.py') @('test','extra80')
Step (Join-Path $holdout 'validate_transfer.py') @()
Step (Join-Path $factor 'report.py') @()

