$ErrorActionPreference = "Stop"
$python = "D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe"
Push-Location $PSScriptRoot
try {
    foreach ($step in @("project.py","training_labels.py","predict.py","score.py","apply.py","verify.py")) {
        & $python $step
        if ($LASTEXITCODE -ne 0) { throw "Failed: $step" }
    }
} finally {
    Pop-Location
}
