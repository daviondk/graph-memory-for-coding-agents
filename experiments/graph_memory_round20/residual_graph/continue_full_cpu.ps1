$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$r='D:/CodexResearch/x20-isetrace-residual'
$py='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$cp='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
$env:PYTHONUTF8='1'
$env:ISE_TOPOLOGY_DEVICE='cpu'
function CallStage([string]$script,[string[]]$stageArgs){
    & $py -B -u "$s/$script" @stageArgs
    if ($LASTEXITCODE){throw "Full CPU pipeline failed at $script $stageArgs"}
}
while (!(Test-Path "$s/full-cpu-complete.json")){
    if(Test-Path "$r/yield-cpu-full"){Write-Output 'Canonical CPU downstream yielded for GPU or operator';exit 0}
    if (!(Get-CimInstance Win32_Process -Filter "Name='python.exe'"|Where-Object {$_.CommandLine -match 'residual_graph[/\\]cpu_full.py'})){throw 'CPU encoder stopped before coverage'}
    Start-Sleep -Seconds 30
}
CallStage 'resume_full.py' @('costs')
CallStage 'cache_audit.py' @('direct')
CallStage 'fit_graph.py' @('pairs')
CallStage 'resume_full.py' @('fit')
CallStage 'infer_graph.py' @('lock')
CallStage 'full_cpu_read.py' @()
CallStage 'export_dev.py' @()
CallStage 'evaluate_graph.py' @()
CallStage 'topology/intervene.py' @('rank')
CallStage 'topology/intervene.py' @('score')
CallStage 'topology/strata.py' @('run')
CallStage 'report.py' @()
CallStage 'seal.py' @()
CallStage 'verify.py' @()

