param([Parameter(Mandatory=$true)][ValidateSet('hash64','full')][string]$Panel,
      [int]$CanonicalProcess=0)
$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$rg=Split-Path -Parent $s
$py='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
(Get-Process -Id $PID).PriorityClass='BelowNormal'
if($Panel -eq 'full'){
    if($CanonicalProcess -eq 0){throw 'Explicit canonical process identifier is required for exclusive GPU scheduling'}
    $deadline=(Get-Date).AddHours(8)
    while((Get-Process -Id $CanonicalProcess -ErrorAction SilentlyContinue) -or !(Test-Path "$rg/topology/forecast-seal.json")){
        if((Get-Date) -ge $deadline){throw 'Canonical evidence not ready within allotted 8 h window'}
        if(!(Get-Process -Id $CanonicalProcess -ErrorAction SilentlyContinue) -and !(Test-Path "$rg/topology/forecast-seal.json")){throw 'Canonical job stopped before its GPU topology seal'}
        Start-Sleep -Seconds 15
    }
    if((Get-PSDrive D).Free -lt 12GB){throw 'Insufficient free space for isolated training and test feature files'}
    & $py -B -c "import torch; assert torch.cuda.is_available(); assert (torch.eye(2,device='cuda') @ torch.eye(2,device='cuda')).sum().item()==2."
    if($LASTEXITCODE){throw 'CUDA preflight failed'}
}
foreach($step in @(@('fit','checkpoint.json'),@('rank','forecast-seal.json'),@('score','matched-comparisons.json'))){
    if(!(Test-Path "$s/$Panel/$($step[1])")){
        & $py -B -u "$s/baseline.py" $step[0] $Panel
        if($LASTEXITCODE){throw "Native ablation $Panel $($step[0]) failed"}
    }
}
& $py -B -u "$s/report.py"
if($LASTEXITCODE){throw 'Ablation report failed'}
