param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$guard=[Threading.Mutex]::new($false,'Local\CodexResearchPublishedReaderCosts')
$owned=$false
try{
    try{$owned=$guard.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
    if(!$owned){throw 'The CPU timing panel is already running'}
    $end=[datetime]::UtcNow.AddHours(4)
    while(!(Test-Path "$PSScriptRoot/MANIFEST_SHA256.json")){
        if([datetime]::UtcNow -gt $end){throw 'The quality comparison did not complete'}
        Start-Sleep -Seconds 15
    }
    Push-Location $PSScriptRoot
    try{
        if(!(Test-Path 'cost-results.json')){
            $dir='D:/CodexResearch/x20-published-reader'
            $p=Start-Process $Python -ArgumentList @('-B','-u',(Join-Path $PSScriptRoot 'costs.py'),'run') -WindowStyle Hidden -WorkingDirectory $PSScriptRoot -PassThru -RedirectStandardOutput "$dir/timings.log" -RedirectStandardError "$dir/timings.err"
            try{
                $p.PriorityClass='BelowNormal'
                if(!$p.WaitForExit(3600000)){throw 'One-hour CPU timing cap'}
                $p.Refresh()
                if($p.ExitCode -ne 0){throw 'Timing panel failed'}
            }finally{if(!$p.HasExited){$p.Kill($true);$p.WaitForExit()};$p.Dispose()}
        }
        & $Python -B report.py
        if($LASTEXITCODE){throw 'Report failed'}
    }finally{Pop-Location}
}finally{if($owned){$guard.ReleaseMutex()};$guard.Dispose()}
