param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$logs='D:/CodexResearch/x20-r27-sentences'
$guard=[Threading.Mutex]::new($false,'Local\CodexResearchSentenceWindow')
$owned=$false
function Note([string]$s){Add-Content -LiteralPath "$logs/queue.log" -Value ("{0:o} {1}" -f [datetime]::UtcNow,$s)}
function Stage([string]$name,[string]$result){
    if(Test-Path (Join-Path $PSScriptRoot $result)){return}
    $p=Start-Process $Python -ArgumentList @('-B','-u',(Join-Path $PSScriptRoot $name)) -WindowStyle Hidden -PassThru -WorkingDirectory $PSScriptRoot -RedirectStandardOutput "$logs/$name.log" -RedirectStandardError "$logs/$name.err"
    Note "start $name pid $($p.Id)"
    try{
        $p.PriorityClass='BelowNormal'
        if(!$p.WaitForExit(7200000)){throw "$name two hour cap"}
        if($p.ExitCode -ne 0 -or !(Test-Path (Join-Path $PSScriptRoot $result))){throw "$name exit $($p.ExitCode)"}
    }finally{if(!$p.HasExited){$p.Kill($true);$p.WaitForExit()};$p.Dispose()}
    Note "done $name"
}
try{
    try{$owned=$guard.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
    if(!$owned){throw 'Existing panel worker owns this request'}
    $end=[datetime]::UtcNow.AddMinutes(40)
    while(!(Test-Path "$PSScriptRoot/native-receipt.json")){
        if([datetime]::UtcNow -gt $end){throw 'Library construction receipt missing'}
        Start-Sleep -Seconds 5
    }
    Stage 'forecast.py' 'forecast-seal.json'
    Stage 'outcomes.py' 'results.json'
    Stage 'verify.py' 'verified.json'
    Stage 'report.py' 'manifest.json'
}catch{Note "failure $_";throw}finally{if($owned){$guard.ReleaseMutex()};$guard.Dispose()}
