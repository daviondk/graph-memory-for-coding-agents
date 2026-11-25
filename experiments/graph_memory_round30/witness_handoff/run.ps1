$ErrorActionPreference='Stop'
$py='D:/CodexResearch/x20-r8-swerank-runtime/venv/Scripts/python.exe'
Push-Location $PSScriptRoot
function Run-Step([string]$Script,[string[]]$Extra){
    & $py $Script @Extra
    if ($LASTEXITCODE -ne 0) {throw "Failed $Script $Extra"}
}
try {
    foreach($p in @('swe','ise','ise4')){
        Run-Step 'inventory.py' @($p)
        Run-Step 'project.py' @($p)
        Run-Step 'predict.py' @($p)
    }
    foreach($p in @('swe','ise','ise4')){Run-Step 'score.py' @($p)}
    Run-Step 'audit.py' @()
    & $py -c "from audit import *; save(D/'ise4-audit.json',audit('ise4'))"
    if($LASTEXITCODE){throw 'four-name independent audit'}
    Run-Step 'physical.py' @()
    & $py -c "from physical import main; main('ise4')"
    if($LASTEXITCODE){throw 'four-name physical audit'}
    foreach($p in @('ise','ise4')){Run-Step 'ise_bytes.py' @($p)}
    Run-Step 'write_report.py' @()
} finally {
    Pop-Location
}
