$ErrorActionPreference="Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING="utf-8"
while (!(Test-Path -LiteralPath acquisition.json)) {Start-Sleep -Seconds 4}
python -u prepare.py
if ($LASTEXITCODE -ne 0) {exit $LASTEXITCODE}
foreach ($stage in @("request","A","seal","B")) {
    python -u experiment.py $stage
    if ($LASTEXITCODE -ne 0) {exit $LASTEXITCODE}
}
python -u analyze.py
exit $LASTEXITCODE
