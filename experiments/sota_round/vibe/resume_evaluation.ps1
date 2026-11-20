param([ValidateSet('main','in_loop')][string]$Phase,[switch]$GradeOnly)
$ErrorActionPreference='Stop'
$here=$PSScriptRoot
if(-not $env:VIBE_RELEASE){$env:VIBE_RELEASE='D:/CodexResearch/x20-official-vibe/VibeMemBench'}
$store=Join-Path (Split-Path $env:VIBE_RELEASE -Parent) 'solver-runtime'
$agentPy=Join-Path $store 'agent-venv/Scripts/python.exe'
$env:TEMP=Join-Path $store 'tmp'
$env:TMP=$env:TEMP
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:PYTHONUTF8='1'
$env:DOCKER_HOST='tcp://127.0.0.1:23767'
$env:VIBE_SOLVER_PROTOCOL=Join-Path $here $(if($Phase -eq 'main'){'prospective_27b.json'}else{'in_loop/protocol.json'})
$plan=Get-Content -Raw -LiteralPath $env:VIBE_SOLVER_PROTOCOL | ConvertFrom-Json
$runs=Join-Path $env:VIBE_RELEASE "outputs/$($plan.runs_subdir)"
$transport=$null
try {
    if(-not $GradeOnly) {
        if($Phase -eq 'in_loop') {
            if(Get-NetTCPConnection -State Listen -LocalPort 18841 -ErrorAction SilentlyContinue){throw 'Intervention transport port already in use'}
            $transport=Start-Process -FilePath $agentPy -ArgumentList @((Join-Path $here 'in_loop/transport.py'),'--store',(Join-Path $store 'in_loop_transport')) -PassThru -WindowStyle Hidden -RedirectStandardError (Join-Path $store 'in_loop_transport.err.log') -RedirectStandardOutput (Join-Path $store 'in_loop_transport.out.log')
            for($i=0;$i -lt 30;$i++){
                try { if((Invoke-RestMethod 'http://127.0.0.1:18841/health').ready){break} } catch {Start-Sleep -Seconds 1}
            }
            if(-not (Invoke-RestMethod 'http://127.0.0.1:18841/health').ready){throw 'Intervention transport not ready'}
        }
        & $agentPy -u (Join-Path $here 'pilot_driver.py')
        if($LASTEXITCODE -ne 0){throw "Pilot driver failed for $Phase"}
    }
    $count=($plan.targets.Count * $plan.methods.Count * $plan.planned_seeds.Count)
    if(@(Get-ChildItem -LiteralPath $runs -Recurse -Filter 'result.json').Count -ne $count){throw "Expected $count completed assignments for $Phase"}
    & $agentPy (Join-Path $here 'reconcile_modern.py')
    if($LASTEXITCODE -ne 0){throw "Ambiguous model receipts for $Phase"}
    & $agentPy (Join-Path $env:VIBE_RELEASE 'scripts/run_eval.py') --runs-dir $runs --dataset (Join-Path $env:VIBE_RELEASE 'benchmark/test.parquet') --image-pool-size 0 --image-workers 1 --seed-workers 1 --eval-script (Join-Path $here 'wsl_eval.py')
    Write-Output "Official grader returned $LASTEXITCODE. Checking each expected row."
    & $agentPy (Join-Path $here 'summarize.py')
    if($LASTEXITCODE -ne 0){throw "Evidence assembly failed for $Phase"}
    if($Phase -eq 'in_loop'){
        & $agentPy (Join-Path $here 'in_loop/audit.py')
        if($LASTEXITCODE -ne 0){throw 'In-loop delivery audit failed'}
    }
} finally {
    if($transport -and -not $transport.HasExited){$transport.Kill()}
}
