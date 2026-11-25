param([Parameter(Mandatory=$true)][ValidateSet("availability","hash64")][string]$Panel)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$upstream = Join-Path (Split-Path $here) "residual_graph/cpu_fallback/$Panel"
$incoming = Join-Path $upstream "forecast-seal.json"
if (-not (Test-Path -LiteralPath $incoming)) { throw "Upstream forecast seal is required." }
$cpu = "D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe"
$hf = "D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe"
$env:OPENBLAS_NUM_THREADS = "1"
function Run-Checked([string]$Interp,[string]$File,[string[]]$Items) {
    & $Interp -B -X utf8 (Join-Path $here $File) @Items
    if ($LASTEXITCODE -ne 0) { throw "$File exited with $LASTEXITCODE" }
}
Run-Checked $cpu "transfer_cpu.py" @($Panel,"inputs","--dir",$upstream,"--pattern","forecasts-rgcn-*.json.gz","--seal",$incoming)
Run-Checked $cpu "transfer_cpu.py" @($Panel,"main")
Run-Checked $cpu "transfer_cpu.py" @($Panel,"duplicate")
Run-Checked $cpu "score.py" @($Panel)
Run-Checked $cpu "strict_render.py" @("predict",$Panel)
Run-Checked $cpu "strict_render.py" @("score",$Panel)
Run-Checked $hf "render_audit.py" @($Panel)
Run-Checked $cpu "clean_sensitivity.py" @($Panel)
Run-Checked $cpu "report.py" @()
Run-Checked $cpu "verify.py" @("--write-manifest","--require-both")
