$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
  $other='D:/CodexResearch/x20-r8-swerank-runtime/venv/Scripts/python.exe'
  $root='D:/CodexResearch/x20-r29-rollback'
  $py="$root/venv/Scripts/python.exe"
  $env:UV_CACHE_DIR="$root/uv-cache"
  & $other fetch.py
  if($LASTEXITCODE -ne 0){throw 'fetch failed'}
  if(-not(Test-Path -LiteralPath $py)){uv venv --python $other "$root/venv"}
  uv pip install --python $py -r "$root/upstream/requirements.txt"
  if($LASTEXITCODE -ne 0){throw 'upstream requirements failed'}
  foreach($stage in @('native.py controlled smoke','native.py adapted smoke','native.py controlled full','native.py adapted full','controls.py controlled','controls.py adapted')){
    $a=$stage.Split(' '); & $py @a
    if($LASTEXITCODE -ne 0){throw $stage}
  }
  foreach($stage in @('evaluate.py controlled','evaluate.py adapted','applied_audit.py')){
    $a=$stage.Split(' '); & $other @a
    if($LASTEXITCODE -ne 0){throw $stage}
  }
} finally {Pop-Location}
