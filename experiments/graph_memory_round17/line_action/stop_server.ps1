$ErrorActionPreference = 'Stop'
$launch = Get-Content -Raw -Encoding utf8 -LiteralPath (Join-Path $PSScriptRoot 'launch.json') | ConvertFrom-Json
$listener = Get-NetTCPConnection -State Listen -LocalPort 18952 -ErrorAction SilentlyContinue
if ($listener) {
    $actual = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $launch.pid)
    if ($listener.OwningProcess -ne $launch.pid -or $actual.ExecutablePath -ne $launch.server.Replace('/','\') -or $actual.CommandLine -notmatch '--port 18952') {
        throw 'Runtime identity changed'
    }
    Stop-Process -Id $launch.pid
}
$alive = [bool](Get-Process -Id $launch.pid -ErrorAction SilentlyContinue)
if ($alive) { throw 'Owned server still running' }
[ordered]@{pid=$launch.pid;port=18952;active=$alive} | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath (Join-Path $PSScriptRoot 'shutdown.json')
