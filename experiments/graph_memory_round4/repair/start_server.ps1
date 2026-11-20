$ErrorActionPreference = 'Stop'
$server = 'D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe'
$model = 'D:/CodexResearch/x20-qwen38-27b/Qwen3.8-27B-UD-Q4_K_M.gguf'
if (Get-NetTCPConnection -State Listen -LocalPort 18904 -ErrorAction SilentlyContinue) {throw 'Port in use'}
if (Test-Path (Join-Path $PSScriptRoot 'launch.json')) {throw 'Existing experiment runtime log'}
$arguments = @('-m',$model,'--alias','qwen38-27b-ud-q4km','--host','127.0.0.1','--port','18904',
    '--jinja','--parallel','1','--ctx-size','4096','--n-gpu-layers','all','--flash-attn','on',
    '--cache-type-k','q8_0','--cache-type-v','q8_0','--batch-size','256','--ubatch-size','128','--cache-ram','0')
$process = Start-Process -FilePath $server -ArgumentList $arguments -WindowStyle Hidden -WorkingDirectory (Split-Path $server) -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.stdout') -RedirectStandardError (Join-Path $PSScriptRoot 'server.stderr') -PassThru
[ordered]@{pid=$process.Id;utc=[DateTime]::UtcNow.ToString('o');server=$server;args=$arguments} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $PSScriptRoot 'launch.json')



