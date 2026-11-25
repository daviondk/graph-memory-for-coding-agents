$dir=$PSScriptRoot
$py='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$ErrorActionPreference='Stop'
if(!(Test-Path -LiteralPath "$dir/prior.json")){ & $py -B -u "$dir/factor.py" prior
if($LASTEXITCODE){throw 'prior'} }
foreach($cohort in @('availability','hash64')){
    if(Test-Path -LiteralPath "$dir/$cohort-results.json"){continue}
    while(!(Test-Path -LiteralPath "$dir/../residual_graph/cpu_fallback/$cohort/fit-lock.json")){Start-Sleep -Seconds 10}
    foreach($stage in @('calibrate','predict')){
        & $py -B -u "$dir/factor.py" $stage $cohort
        if($LASTEXITCODE){throw "$stage $cohort"}
    }
    & $py -B -u "$dir/evaluate.py" $cohort
    if($LASTEXITCODE){throw "evaluation $cohort"}
}
