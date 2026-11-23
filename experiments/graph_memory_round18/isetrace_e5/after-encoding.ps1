$ErrorActionPreference='Stop'
$here=$PSScriptRoot
$runtime='D:/CodexResearch/x20-isetrace-e5-gpu'
$py='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
$env:PYTHONUTF8='1'
while (!(Test-Path -LiteralPath "$here/cost-fp32.json")) {
    $p=Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {$_.CommandLine -like "*isetrace_e5/encode.py*run*" -or $_.CommandLine -like "*isetrace_e5\encode.py*run*"}
    if (!$p){throw 'Encoder exited before it wrote the expected cost receipt.'}
    Start-Sleep -Seconds 10
}
foreach($step in @('forecasts.py run','placebo_e5.py predict','budget_grid.py predict','cpu_check.py','evaluate.py','placebo_e5.py score','budget_grid.py score')){
    $segments=$step.Split(' ')
    $args0=@()
    if ($segments.Length -gt 1){$args0=@($segments[1])}
    $watch=[Diagnostics.Stopwatch]::StartNew()
    & $py -B "$here/$($segments[0])" @args0
    if ($LASTEXITCODE -ne 0){throw "Failed $step"}
    Write-Output ("{0} {1:N3} s" -f $step,$watch.Elapsed.TotalSeconds)
}
