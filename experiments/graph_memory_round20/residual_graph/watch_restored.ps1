param([Parameter(Mandatory=$true)][int]$NativeProcess,[Parameter(Mandatory=$true)][string]$LogName)
$ErrorActionPreference='Stop'
$r='D:/CodexResearch/x20-isetrace-residual'
$log=Join-Path "$r/logs" $LogName
$py='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONUTF8='1'
$deadline=(Get-Date).AddHours(8)
$hot=0
function Halt-OwnRun([string]$Reason){
    $owner=Get-CimInstance Win32_Process -Filter "ProcessId=$NativeProcess"
    if (!$owner -or $owner.CommandLine -notmatch 'resume_after_device.ps1'){ throw 'Parent process is not the expected native GPU worker.' }
    Add-Content -Encoding utf8 -LiteralPath $log -Value (@{stop=$Reason;utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json -Compress)
    # Only this calculation's full subprocess tree. SQLite commits each completed block.
    $owned=@($NativeProcess)
    $snapshot=Get-CimInstance Win32_Process
    for($i=0;$i -lt $owned.Count;$i++){
        $owned+=@($snapshot | Where-Object {$_.ParentProcessId -eq $owned[$i]} | Select-Object -ExpandProperty ProcessId)
    }
    [array]::Reverse($owned)
    foreach($child in $owned){Stop-Process -Id $child -ErrorAction SilentlyContinue}
    throw $Reason
}
while(Get-Process -Id $NativeProcess -ErrorAction SilentlyContinue){
    $native=Get-CimInstance Win32_Process -Filter "ProcessId=$NativeProcess"
    if($native.CommandLine -notmatch 'resume_after_device.ps1'){throw 'Producer PID was reused.'}
    $v=& nvidia-smi --query-gpu=temperature.gpu,memory.used,memory.total,utilization.gpu,power.draw --format=csv,noheader,nounits
    if($LASTEXITCODE -eq 0 -and $v){
        $vals=@($v[0] -split ',')
        if($v -is [string]){$vals=@($v -split ',')}
        $temp=[int]$vals[0]
        $hot=if($temp -ge 89){$hot+1}else{0}
        $entry=@{utc=[DateTime]::UtcNow.ToString('o');temperature_C=$temp;used_MiB=[int]$vals[1];total_MiB=[int]$vals[2];utilization_pct=[int]$vals[3];power_W=$vals[4].Trim()}
        Add-Content -Encoding utf8 -LiteralPath $log -Value ($entry | ConvertTo-Json -Compress)
        if($hot -ge 2){Halt-OwnRun 'GPU reached 89 C in two successive readings.'}
    }
    if((Get-Date) -gt $deadline){Halt-OwnRun 'Native uninterrupted budget of eight hours reached.'}
    if((Get-PSDrive D).Free -lt 7GB){Halt-OwnRun 'D: free-space reserve reached.'}
    if((Test-Path "$PSScriptRoot/gpu-resume-ft.json") -and (Test-Path "$PSScriptRoot/cpu_fallback/hash64/cpu-encoding.json") -and !(Test-Path "$PSScriptRoot/cost-ft.json")){
        & $py -B -u "$PSScriptRoot/recovery_costs.py" ft
        if($LASTEXITCODE){throw 'Premature FT receipt rejected.'}
    }
    Start-Sleep -Seconds 30
}
