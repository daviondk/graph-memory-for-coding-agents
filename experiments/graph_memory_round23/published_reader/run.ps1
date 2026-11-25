param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7){throw 'Use PowerShell 7 for bounded process-tree control'}
$private='D:/CodexResearch/x20-published-reader'
$env:PYTHONUTF8='1'
$guard=[Threading.Mutex]::new($false,'Local\CodexResearchPublishedReaderCPU')
$owned=$false
function Note([string]$message){Add-Content -LiteralPath "$private/run.log" -Value ("{0:o} {1}" -f [datetime]::UtcNow,$message)}
function Step([string]$file,[string]$stage,[string]$receipt,[int]$minutes){
    if(Test-Path -LiteralPath "$PSScriptRoot/$receipt"){return}
    $tag="$stage-$file-$([datetime]::UtcNow.Ticks)"
    $p=Start-Process $Python -ArgumentList @('-B','-u',(Join-Path $PSScriptRoot $file),$stage) -WindowStyle Hidden -PassThru -WorkingDirectory $PSScriptRoot -RedirectStandardOutput "$private/$tag.log" -RedirectStandardError "$private/$tag.err"
    $p.PriorityClass='BelowNormal';$end=[datetime]::UtcNow.AddMinutes($minutes)
    Note "start $tag pid $($p.Id)"
    try{
        while(!$p.WaitForExit(10000)){
            if([datetime]::UtcNow -gt $end -or (Get-PSDrive D).Free -lt 7GB){throw 'Scoped resource bound reached'}
        }
        $p.Refresh()
        if($p.ExitCode -ne 0 -or !(Test-Path -LiteralPath "$PSScriptRoot/$receipt")){throw "$tag failed with exit $($p.ExitCode)"}
    }finally{if(!$p.HasExited){$p.Kill($true);$p.WaitForExit()};$p.Dispose()}
    Note "finish $tag"
}
try{
    try{$owned=$guard.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
    if(!$owned){throw 'A reader queue already owns the run'}
    foreach($stage in @('dev','test')){
        Step 'inputs.py' $stage "$stage-inputs.json" 15
        Step 'predict.py' $stage "$stage-seal.json" 150
        Step 'score.py' $stage "$stage-results.json" 20
    }
    Note 'all comparisons complete'
}catch{Note "error $_";throw}finally{if($owned){$guard.ReleaseMutex()};$guard.Dispose()}
