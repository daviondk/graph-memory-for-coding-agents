param([string]$Python="D:/CodexResearch/x20-r8-swerank-runtime/venv/Scripts/python.exe")
$ErrorActionPreference="Stop"
foreach ($name in @("source.py","download_events.py","extract.py","predict.py","score.py","audit.py")) {
    & $Python -B -u (Join-Path $PSScriptRoot $name)
    if ($LASTEXITCODE -ne 0) { throw "Failed $name with exit code $LASTEXITCODE" }
}
