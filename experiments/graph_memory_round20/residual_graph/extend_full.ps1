param([Parameter(Mandatory=$true)][int]$CanonicalProcess,[Parameter(Mandatory=$true)][int]$AblationProcess)
$ErrorActionPreference='Stop'
$rg=$PSScriptRoot
$series=Split-Path -Parent $rg
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$hf='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='1'
(Get-Process -Id $PID).PriorityClass='BelowNormal'
function Wait-Stage([int]$Owner,[string]$Target){
    $deadline=(Get-Date).AddHours(8)
    while((Get-Process -Id $Owner -ErrorAction SilentlyContinue) -or !(Test-Path -LiteralPath $Target)){
        if((Get-Date) -gt $deadline){throw "stage $Target not ready within window"}
        if(!(Get-Process -Id $Owner -ErrorAction SilentlyContinue) -and !(Test-Path -LiteralPath $Target)){throw "stage $Target exited without receipt"}
        Start-Sleep -Seconds 10
    }
}
function Run([string]$Interp,[string]$Program,[string[]]$Params){
    & $Interp -B -X utf8 $Program @Params
    if($LASTEXITCODE){throw "$Program $Params failed"}
}
Wait-Stage $CanonicalProcess "$rg/topology/strata-results.json"
$dir="$series/graph_trigger"
$d=Get-Content -LiteralPath "$rg/dev500-rgcn-lock.json" -Raw|ConvertFrom-Json
if(!(Test-Path "$dir/canonical-results.json")){
    Run $cpu "$dir/gate.py" @('fit',"$rg/dev500-pu-rgcn-ranks.json.gz",$d.ranks,'canonical')
    Run $cpu "$dir/gate.py" @('predict','canonical')
    Run $cpu "$dir/evaluate.py" @('canonical',$rg,'forecasts-rgcn-*.json.gz',"$rg/forecast-seal.json")
}
Run $cpu "$dir/controls.py" @('canonical')
Run $hf "$dir/runtime_canonical.py" @()
Run $cpu "$dir/report.py" @()
Run $cpu "$dir/verify.py" @('--write-manifest')
$u="$series/union_read"
if(!(Test-Path "$u/rgcn-render-audit.json")){
    Run $cpu "$u/pack.py" @('plan','rgcn')
    Run $cpu "$u/pack.py" @('predict','rgcn')
    Run $cpu "$u/overlap_control.py" @('plan','rgcn')
    Run $cpu "$u/overlap_control.py" @('predict','rgcn')
    Run $cpu "$u/score.py" @('rgcn')
    Run $cpu "$u/strict_render.py" @('predict','rgcn')
    Run $cpu "$u/strict_render.py" @('score','rgcn')
    Run $hf "$u/render_audit.py" @('rgcn')
}
Run $cpu "$u/clean_sensitivity.py" @('rgcn')
Run $cpu "$u/report.py" @()
Run $cpu "$u/verify.py" @('--write-manifest','--require-both')
$flow="$rg/evidence_flow"
Run $cpu "$flow/analyze.py" @('score','full')
Run $cpu "$flow/diversify.py" @('predict','full')
Run $cpu "$flow/diversify.py" @('score','full')
Run $cpu "$flow/diversity_report.py" @()
Run $cpu "$flow/report.py" @()
Run $cpu "$flow/verify.py" @()
Run $cpu "$flow/verify_diversity.py" @()
$mo="$rg/official_modes"
Run $cpu "$mo/modes.py" @('full')
Wait-Stage $AblationProcess "$rg/adjacency_control/full/matched-comparisons.json"
Run $cpu "$mo/modes.py" @('no_next_full')
Run $cpu "$mo/report.py" @()
Run $cpu "$rg/report.py" @()
Run $cpu "$rg/seal.py" @()
Run $cpu "$rg/verify.py" @()

