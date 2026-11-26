$ErrorActionPreference='Stop'
$runtime='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$solo=[Threading.Mutex]::new($false,'Local\CodexResearchR40QwenPanel214')
$owned=$false
try {
    try {$owned=$solo.WaitOne(0)} catch [Threading.AbandonedMutexException] {$owned=$true}
    if (!$owned) {throw 'R40 already running'}
    if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'gpu-seal.json'))) {
        $once=$true
        while ($true) {
            & (Join-Path $PSScriptRoot 'gpu.ps1')
            if ($LASTEXITCODE -eq 0) {break}
            if ($LASTEXITCODE -ne 2) {throw 'GPU evaluation failed'}
            if ($once) {Write-Output 'Waiting for the running GPU experiments to release the shared mutex';$once=$false}
            Start-Sleep -Seconds 40
        }
    }
    & $runtime -B -u (Join-Path $PSScriptRoot 'fusion.py') fuse
    if ($LASTEXITCODE -ne 0) {throw 'Fusion sealing failed'}
    & $runtime -B -u (Join-Path $PSScriptRoot 'grade_panel.py')
    if ($LASTEXITCODE -ne 0) {throw 'Primary evaluation failed'}
    & $runtime -B -u (Join-Path $PSScriptRoot 'fusion_grade.py')
    if ($LASTEXITCODE -ne 0) {throw 'Additional evaluation failed'}
    & $runtime -B -u (Join-Path $PSScriptRoot 'verify.py') --final
    if ($LASTEXITCODE -ne 0) {throw 'Final verification failed'}
} finally {
    if ($owned) {$solo.ReleaseMutex()}
    $solo.Dispose()
}
