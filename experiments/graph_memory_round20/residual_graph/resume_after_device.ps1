$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$r='D:/CodexResearch/x20-isetrace-residual'
$gpu='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
$env:PYTHONUTF8='1'
$env:ISE_TOPOLOGY_DEVICE='cuda'
& $gpu -B -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(), (torch.eye(2,device='cuda') @ torch.eye(2,device='cuda')).cpu())"
if($LASTEXITCODE){throw 'GPU is unavailable; CPU work is continuing'}
[IO.File]::WriteAllText("$r/yield-cpu-full",'Transition from resumable CPU encoder to restored GPU; current transaction may complete.')
while(Get-CimInstance Win32_Process -Filter "Name='python.exe'"|Where-Object {$_.CommandLine -match 'residual_graph[/\\]cpu_full.py'}){Start-Sleep -Seconds 3}
function Stage([string]$file,[string[]]$arglist){
    & $gpu -B -u "$s/$file" @arglist
    if($LASTEXITCODE){throw "Recovered GPU run failed at $file $arglist"}
}
if(!(Test-Path "$s/gpu-resume-ft.json")){Stage 'resume_full.py' @('gpu','ft')}
if(!(Test-Path "$s/gpu-resume-base.json")){Stage 'resume_full.py' @('gpu','base')}
Stage 'resume_full.py' @('costs')
Stage 'cache_audit.py' @('direct')
if(!(Test-Path "$s/pair-inventory.json")){Stage 'fit_graph.py' @('pairs')}
if(!(Test-Path "$s/checkpoint.json")){Stage 'fit_graph.py' @('fit')}
if(!(Test-Path "$s/prediction-plan.json")){Stage 'infer_graph.py' @('lock')}
if(!(Test-Path "$s/forecast-seal.json")){Stage 'infer_graph.py' @('infer')}
Stage 'export_dev.py' @()
Stage 'evaluate_graph.py' @()
Stage 'topology/intervene.py' @('rank')
Stage 'topology/intervene.py' @('score')
Stage 'topology/strata.py' @('run')
Stage 'report.py' @()
Stage 'seal.py' @()
Stage 'verify.py' @()

