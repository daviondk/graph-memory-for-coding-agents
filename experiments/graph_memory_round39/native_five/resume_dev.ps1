$ErrorActionPreference='Stop'
$dir=(Resolve-Path (Join-Path $PSScriptRoot '../../graph_memory_round34/dev_metric')).Path
$work=Split-Path -Parent (Split-Path -Parent $dir)
$canonical=Join-Path $work 'graph_memory_round22/native_multiseed/official580'
$python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$private='D:/CodexResearch/x20-r34-dev-metric'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
function Step($script,$params,$receipt){
    if(Test-Path -LiteralPath $receipt){return}
    $tag=($params -join '-')+'-'+[DateTime]::UtcNow.Ticks
    $p=Start-Process -WindowStyle Hidden -FilePath $python -ArgumentList (@('-u','-B',(Join-Path $dir $script))+$params) -PassThru -WorkingDirectory $dir -RedirectStandardOutput "$private/$tag.log" -RedirectStandardError "$private/$tag.err"
    $hot=0
    try {
        while(!$p.WaitForExit(10000)){
            $temperature=@(& nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits)
            if($LASTEXITCODE -eq 0 -and $temperature.Count -gt 0 -and [int]$temperature[0] -ge 89){$hot++}else{$hot=0}
            if($hot -ge 2 -or (Get-PSDrive D).Free -lt 7GB){throw "Resource ceiling at $tag"}
        }
        $p.Refresh()
        if($p.ExitCode -ne 0 -or !(Test-Path -LiteralPath $receipt)){throw "Check $private/$tag.err and $receipt"}
    } finally {if(!$p.HasExited){$p.Kill($true);$p.WaitForExit()};$p.Dispose()}
}
$queue=[Threading.Mutex]::new($false,'Local\CodexResearchBudgetEpochs')
$gpu=[Threading.Mutex]::new($false,'Local\CodexResearchGraphMemoryFiveSeed')
$owned=$false
$device=$false
try {
    try{$owned=$queue.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
    if(!$owned){throw 'Budget epoch replay already active'}
    & $python -B (Join-Path $dir 'verify.py')
    if($LASTEXITCODE -ne 0){throw 'Invalid protocol or CPU smoke receipt'}
    while(!(Test-Path "$canonical/five-seed-results.json")){Start-Sleep -Seconds 30}
    while(!$device){try{$device=$gpu.WaitOne(15000)}catch [Threading.AbandonedMutexException]{$device=$true}}
    $seeds=@(13,17,29,37,41)
    $arms=@('full_rgcn','wo_chunk_adjacency')
    foreach($seed in $seeds){foreach($arm in $arms){
        Step 'tap.py' @("$seed",$arm) "$dir/dev-selection-$seed-$arm.json"
    }}
    Step 'test_selection.py' @('seal') "$dir/all-dev-seal.json"
    foreach($seed in $seeds){foreach($arm in $arms){
        Step 'test_selection.py' @('rank',"$seed",$arm) "$dir/test-rank-seal-$seed-$arm.json"
        Step 'test_selection.py' @('score',"$seed",$arm) "$dir/test-results-$seed-$arm.json.gz"
    }}
    $gpu.ReleaseMutex();$device=$false
    while(!(Test-Path "$dir/../native_comparison/outcomes-41.json.gz")){Start-Sleep -Seconds 15}
    Step 'test_selection.py' @('compare') "$dir/budget-selected-comparison.json"
    & $python -B (Join-Path $dir 'verify.py') --complete
    if($LASTEXITCODE -ne 0){throw 'Final outcome or ledger verification failed'}
}finally {
    if($device){$gpu.ReleaseMutex()}
    if($owned){$queue.ReleaseMutex()}
    $gpu.Dispose();$queue.Dispose()
}
