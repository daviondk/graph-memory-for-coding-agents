$ErrorActionPreference = 'Stop'
$experiment = Split-Path -Parent $MyInvocation.MyCommand.Path
$privateRun = 'D:/CodexResearch/x20-r49-qa-transfer'
$binary = 'D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe'
$weights = 'D:/CodexResearch/x20-published-output-audit/Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
$runner = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$port = 18896
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw 'Port already occupied' }
$argsForServer = @('-m',$weights,'--host','127.0.0.1','--port',"$port",'--parallel','1','--ctx-size','1024','--n-gpu-layers','all','--flash-attn','on','--threads','4','--no-warmup')
$process = Start-Process -PassThru -WindowStyle Hidden -FilePath $binary -ArgumentList $argsForServer -WorkingDirectory $privateRun -RedirectStandardOutput "$privateRun/server.stdout" -RedirectStandardError "$privateRun/server.stderr"
$process.Id | Set-Content -Path "$privateRun/qa.pid"
try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if ($process.HasExited) { throw 'QA server exited before initialization' }
        try { $health = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 2; $ready = ($health.status -eq 'ok') } catch { $ready = $false }
        if ($ready) { break }
        Start-Sleep -Milliseconds 400
    }
    if (-not $ready) { throw 'QA server failed to become ready' }
    & $runner -B "$experiment/inputs.py"
    if ($LASTEXITCODE) { throw 'Input preparation failed' }
    & $runner -B "$experiment/generate.py"
    if ($LASTEXITCODE) { throw 'Generation failed' }
} finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id; $process.WaitForExit() }
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw 'QA listener still present' }
}
