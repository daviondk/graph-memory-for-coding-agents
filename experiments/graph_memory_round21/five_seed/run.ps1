param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$here=$PSScriptRoot
$work=Split-Path (Split-Path $here -Parent) -Parent
$native=Join-Path $work 'graph_memory_round20/residual_graph'
$private='D:/CodexResearch/x20-isetrace-multiseed'
$log=Join-Path $private 'queue.log'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:PYTHONUTF8='1'
$jobTemp=Join-Path $private 'tmp'
[void](New-Item -ItemType Directory -Force -Path $jobTemp)
$env:TEMP=$jobTemp
$env:TMP=$jobTemp
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'

function Record([string]$Line){
    Add-Content -LiteralPath $log -Encoding UTF8 -Value ("{0:o} {1}" -f [DateTime]::UtcNow,$Line)
}

function Step([string]$Script,[string[]]$Params,[string]$Seal){
    if(Test-Path -LiteralPath $Seal){return}
    $tag=$Params -join '-'
    Record "start $Script $tag"
    $output=Join-Path $private "$tag.stdout.log"
    $errorLog=Join-Path $private "$tag.stderr.log"
    & $Python -B -u (Join-Path $here $Script) @Params 1>>$output 2>>$errorLog
    if($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $Seal)){throw "$Script $tag returned $LASTEXITCODE, expected $Seal. See $errorLog"}
    Record "finished $Script $tag"
}
function Wait-GPU{
    $required=@((Join-Path $native 'forecast-seal.json'),(Join-Path $native 'adjacency_control/full/forecast-seal.json'))
    Record 'waiting for both sealed native GPU runs and their launchers to exit'
    while($true){
        $missing=@($required | Where-Object {!(Test-Path -LiteralPath $_)})
        if($missing.Count -eq 0){
            $other=@(Get-CimInstance Win32_Process | Where-Object {
                $_.ProcessId -ne $PID -and
                ($_.Name -in @('powershell.exe','pwsh.exe','python.exe')) -and
                ($_.CommandLine -match '(?i)residual_graph[/\\]resume_after_device\.ps1|residual_graph[/\\]adjacency_control[/\\]run_ablation\.ps1.+full|residual_graph[/\\](resume_full|fit_graph)\.py')
            })
            if($other.Count -eq 0){break}
        }
        Start-Sleep -Seconds 15
    }
    Record 'native GPU gate released'
}
$gate=[Threading.Mutex]::new($false,'Local\CodexResearchGraphMemoryFiveSeed')
$owned=$false
try{
    try{$owned=$gate.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
    if(!$owned){throw 'Another five-seed runner is active'}
    $status=Join-Path $private 'queue.pid'
    Set-Content -LiteralPath $status -Value $PID -Encoding ascii
    Step 'study.py' @('plan') (Join-Path $here 'plan.json')
    Step 'study.py' @('inputs') (Join-Path $here 'inputs.json')
    Step 'score.py' @('predict','13') (Join-Path $here 'seed-13/forecast-seal.json')
    Step 'score.py' @('score','13') (Join-Path $here 'seed-13/results.json')
    Step 'score.py' @('aggregate') (Join-Path $here 'interim-1-results.json')
    foreach($id in @(17,29,37,41)){
        Step 'study.py' @('pairs',"$id") (Join-Path $here "seed-$id/pairs.json")
    }
    Wait-GPU
    foreach($id in @(17,29,37,41)){
        Step 'study.py' @('fit',"$id") (Join-Path $here "seed-$id/model.json")
        Step 'study.py' @('encode',"$id") (Join-Path $here "seed-$id/embeddings.json")
        Step 'study.py' @('calibrate',"$id") (Join-Path $here "seed-$id/calibration.json")
        Step 'score.py' @('predict',"$id") (Join-Path $here "seed-$id/forecast-seal.json")
        Step 'score.py' @('score',"$id") (Join-Path $here "seed-$id/results.json")
        & $Python -B -u (Join-Path $here 'score.py') aggregate
        if($LASTEXITCODE){throw "Aggregate after seed $id failed"}
        Record "aggregate through seed $id"
    }
    if(!(Test-Path -LiteralPath (Join-Path $here 'five-seed-results.json'))){throw 'Final estimate missing'}
    Record 'all five model seeds completed'
}
catch{Record "error $_";throw}
finally{if($owned){$gate.ReleaseMutex()};$gate.Dispose()}

