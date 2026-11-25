$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
  & ./fetch.ps1
  $py='D:/CodexResearch/x20-r8-swerank-runtime/venv/Scripts/python.exe'
  foreach ($stage in @('prepare.py','prepare_loc.py','predict.py natural','predict.py loc','score.py natural','score.py loc','audit.py','report.py')) {
    $arguments=$stage.Split(' ')
    & $py @arguments
    if ($LASTEXITCODE -ne 0) {throw "Stage failed: $stage"}
  }
} finally {Pop-Location}
