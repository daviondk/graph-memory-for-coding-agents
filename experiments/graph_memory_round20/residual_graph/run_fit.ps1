$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$r='D:/CodexResearch/x20-isetrace-residual/logs'
$gpu='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
function Await-Vector([string]$name) {
    while (!(Test-Path "$s/$name")){
        if (!(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object {$_.CommandLine -match 'run_vectors.ps1'})){throw "Vector run exited before $name"}
        Start-Sleep -Seconds 5
    }
}
Await-Vector 'cost-dev.json'
& $cpu -B -u "$s/data.py"
if ($LASTEXITCODE){throw 'dev PU rank failed'}
Await-Vector 'cost-base.json'
& $gpu -B -u "$s/fit_graph.py" pairs
if ($LASTEXITCODE){throw 'native pair mining failed'}
& $gpu -B -u "$s/fit_graph.py" fit
if ($LASTEXITCODE){throw 'native fit failed'}
& $gpu -B -u "$s/infer_graph.py" lock
if ($LASTEXITCODE){throw 'forecast lock failed'}
& $gpu -B -u "$s/infer_graph.py" infer
if ($LASTEXITCODE){throw 'source-only inference failed'}
& $cpu -B -u "$s/evaluate_graph.py"
if ($LASTEXITCODE){throw 'scoring failed'}

