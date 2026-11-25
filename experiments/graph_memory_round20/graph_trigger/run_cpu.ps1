param([Parameter(Mandatory=$true)][ValidateSet("availability","hash64")][string]$Panel)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$upstream = Join-Path (Split-Path $here) "residual_graph/cpu_fallback/$Panel"
$incoming = Join-Path $upstream "forecast-seal.json"
if (-not (Test-Path -LiteralPath $incoming)) { throw "Upstream forecast seal is required." }
$cpu = "D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe"
$env:OPENBLAS_NUM_THREADS = "1"
$devName = "dev500-pu-rgcn-ranks.json.gz"
$seal = Get-Content -Raw -LiteralPath $incoming | ConvertFrom-Json
$devSHA = $seal.files.$devName
if (-not $devSHA) { throw "Dev rank hash missing from upstream." }
function Run-Checked([string]$File,[string[]]$Items) {
    & $cpu -B -X utf8 (Join-Path $here $File) @Items
    if ($LASTEXITCODE -ne 0) { throw "$File exited with $LASTEXITCODE" }
}
Run-Checked "gate.py" @("fit",(Join-Path $upstream $devName),$devSHA,$Panel)
Run-Checked "gate.py" @("predict",$Panel)
Run-Checked "evaluate.py" @($Panel,$upstream,"forecasts-rgcn-*.json.gz",$incoming)
Run-Checked "controls.py" @($Panel)
$torch = "D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe"
& $torch -B -X utf8 (Join-Path $here "runtime_probe.py") $Panel
if ($LASTEXITCODE -ne 0) { throw "CPU runtime probe exited with $LASTEXITCODE" }
if ($Panel -eq "hash64") { Run-Checked "transfer_audit.py" @() }
Run-Checked "report.py" @()
Run-Checked "verify.py" @("--write-manifest")
