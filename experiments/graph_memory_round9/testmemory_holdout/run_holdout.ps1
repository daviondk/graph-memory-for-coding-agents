$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$py='D:/CodexResearch/x20-round9-test311-runtime/venv/Scripts/python.exe'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$env:PYTHONHASHSEED='0'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:TEMP='D:/CodexResearch/x20-round9-testholdout-runtime'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
foreach ($stage in 'collect','predict','testmon_pair','score') {
    & $py -B "$stage.py" *> "$stage.stage.log"
    if ($LASTEXITCODE -ne 0) { Get-Content "$stage.stage.log" -Tail 12; exit $LASTEXITCODE }
    Write-Output "$stage completed"
}
