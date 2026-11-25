param([Parameter(Mandatory=$true)][ValidateSet('hash64','availability')]$Cohort)
$root=$PSScriptRoot
$py='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$ErrorActionPreference='Stop'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='1'
function Step([string]$script,[string[]]$argsList){
    & $py -B -u (Join-Path $root $script) @argsList
    if($LASTEXITCODE){throw "$script $argsList exited $LASTEXITCODE"}
}
while (!(Test-Path -LiteralPath "$root/residual_graph/cpu_fallback/$Cohort/fit-lock.json")) {Start-Sleep -Seconds 10}
Step 'fine_subset/limited.py' @($Cohort,'fit')
Step 'fine_subset/limited.py' @($Cohort,'dense')
Step 'assess.py' @("fine_subset/$Cohort",'dense')
while (!(Test-Path -LiteralPath "$root/residual_graph/cpu_fallback/$Cohort/forecast-seal.json")) {Start-Sleep -Seconds 10}
$mode="rgcn_$Cohort"
Step 'fine_subset/limited.py' @($Cohort,$mode)
Step 'assess.py' @("fine_subset/$Cohort",$mode)
Step 'render_audit.py' @('predict',"fine_subset/$Cohort",$mode)
Step 'render_audit.py' @('score',"fine_subset/$Cohort",$mode)
foreach ($folder in @('fine_read','fine_lextrain')){
    Step 'fine_subset/limited.py' @($Cohort,$folder)
    Step 'assess.py' @($folder,$mode)
}
