param([int]$InferenceProcess = 0)
$ErrorActionPreference = 'Stop'
$jobDir = $PSScriptRoot
$pyExe = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
if ($InferenceProcess -gt 0 -and -not (Test-Path -LiteralPath (Join-Path $jobDir 'reader-lock.json'))) {
    $proc = Get-Process -Id $InferenceProcess -ErrorAction SilentlyContinue
    if ($proc) { $proc.WaitForExit() }
}
if (-not (Test-Path -LiteralPath (Join-Path $jobDir 'reader-lock.json'))) {
    throw 'Inference has no final reader lock. Resume infer.py and re-run finish.ps1.'
}
Push-Location -LiteralPath $jobDir
try {
    & $pyExe -B open_sql.py
    if ($LASTEXITCODE -ne 0) { throw 'SQL open failed.' }
    & $pyExe -B evaluate_open.py
    if ($LASTEXITCODE -ne 0) { throw 'Primary scoring failed.' }
    & $pyExe -B candidate_controls.py score
    if ($LASTEXITCODE -ne 0) { throw 'Secondary scoring failed.' }
}
finally { Pop-Location }
