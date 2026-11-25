param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$private='D:/CodexResearch/x20-published-reader'
$guard=[Threading.Mutex]::new($false,'Local\CodexResearchPublishedReaderScore')
$owned=$false
try{
    try{$owned=$guard.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
    if(!$owned){throw 'Another finalization process owns the run'}
    $deadline=[datetime]::UtcNow.AddHours(4)
    while(!(Test-Path -LiteralPath "$PSScriptRoot/test-results.json")){
        if([datetime]::UtcNow -gt $deadline){throw 'Original primary not completed within bound'}
        Start-Sleep -Seconds 15
    }
    Push-Location $PSScriptRoot
    try{
        if(!(Test-Path -LiteralPath 'test-equal-spend-results.json')){& $Python -B equal_spend.py test;if($LASTEXITCODE){throw 'equal spending'}}
        & $Python -B verify.py dev test;if($LASTEXITCODE){throw 'verification'}
        & $Python -B report.py;if($LASTEXITCODE){throw 'report'}
    }finally{Pop-Location}
}finally{if($owned){$guard.ReleaseMutex()};$guard.Dispose()}
