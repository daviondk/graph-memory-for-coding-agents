$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$py='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
$env:PYTHONUTF8='1'
while(!(Test-Path -LiteralPath "$s/encoding-cost.json")){
    $p=Get-CimInstance Win32_Process -Filter "Name='python.exe'"|Where-Object {$_.CommandLine -match 'bounded_dense[/\\]retrieve_blocks.py.+encode'}
    if(!$p){throw 'Encoder exited before receipt'}
    Start-Sleep -Seconds 10
}
& $py -B -u "$s/retrieve_blocks.py" predict
if($LASTEXITCODE -ne 0){throw 'Forecast failed'}
& $py -B -u "$s/evaluate_blocks.py"
if($LASTEXITCODE -ne 0){throw 'Scoring failed'}
