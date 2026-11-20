param(
    [string]$LlamaServer='D:/CodexResearch/x20-4-27b-runtime/bin/llama-server.exe',
    [string]$ModelPath='D:/CodexResearch/x20-qwen38-27b/Qwen3.8-27B-UD-Q4_K_M.gguf'
)
$ErrorActionPreference='Stop'
$runFolder=Join-Path $PSScriptRoot 'runtime'
New-Item -ItemType Directory -Force $runFolder | Out-Null
$serveArgs=@('-m',('"' + (Resolve-Path -LiteralPath $ModelPath).Path + '"'),'--alias','qwen38-27b-ud-q4km','--host','127.0.0.1','--port','18961','--jinja','--parallel','1','--ctx-size','8192','--n-gpu-layers','all','--flash-attn','on','--cache-type-k','q8_0','--cache-type-v','q8_0','--batch-size','256','--ubatch-size','128','--cache-ram','0')
$sv=Start-Process -FilePath $LlamaServer -ArgumentList $serveArgs -WindowStyle Hidden -RedirectStandardError (Join-Path $runFolder 'server.stderr') -RedirectStandardOutput (Join-Path $runFolder 'server.stdout') -PassThru
Get-CimInstance Win32_Process -Filter "ProcessId = $($sv.Id)" | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json | Set-Content (Join-Path $runFolder 'launch.json') -Encoding utf8

