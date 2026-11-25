param([string]$Python='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe')
$ErrorActionPreference='Stop'
$dir=$PSScriptRoot
$source=Join-Path (Split-Path (Split-Path $dir -Parent) -Parent) 'graph_memory_round20/residual_graph/adjacency_control/full/forecast-seal.json'
while(!(Test-Path -LiteralPath $source)){Start-Sleep -Seconds 8}
if(!(Test-Path -LiteralPath (Join-Path $dir 'no-next-render-seal.json'))){
    & $Python -B -u (Join-Path $dir 'control.py') predict
    if($LASTEXITCODE){throw "forecast failed $LASTEXITCODE"}
}
if(!(Test-Path -LiteralPath (Join-Path $dir 'results.json'))){
    & $Python -B -u (Join-Path $dir 'control.py') score
    if($LASTEXITCODE){throw "evaluation failed $LASTEXITCODE"}
}


& $Python -B (Join-Path $dir 'verify.py')
if($LASTEXITCODE){throw 'Independent interval audit failed'}
& $Python -B (Join-Path $dir 'report.py')
if($LASTEXITCODE){throw 'Report sealing failed'}
