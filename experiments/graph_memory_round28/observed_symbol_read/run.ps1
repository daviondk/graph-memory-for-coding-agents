$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
  & ../../graph_memory_round27/code_boundary/fetch.ps1
  $py='D:/CodexResearch/x20-r8-swerank-runtime/venv/Scripts/python.exe'
  foreach($stage in @('prepare.py swe','prepare.py loc','predict28.py swe','predict28.py loc','score28.py swe','score28.py loc','physical.py','lexer_audit.py','audit28.py','report28.py')) {
    $arguments=$stage.Split(' ')
    & $py @arguments
    if($LASTEXITCODE -ne 0){throw "Stage failed: $stage"}
  }
} finally {Pop-Location}
