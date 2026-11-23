$ErrorActionPreference='Stop'
$private='D:/CodexResearch/x20-isetrace-runtime/writer-action-private'
$exe='D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe'
$model='D:/CodexResearch/x20-qwen38-27b/Qwen3.8-27B-UD-Q4_K_M.gguf'
if(Get-NetTCPConnection -State Listen -LocalPort 18952 -ErrorAction SilentlyContinue){throw 'Port 18952 is in use'}
$settings=@('-m',$model,'--alias','qwen38-27b-ud-q4km','--host','127.0.0.1','--port','18952','--jinja','--parallel','1','--ctx-size','16384','--n-gpu-layers','all','--flash-attn','on','--cache-type-k','q8_0','--cache-type-v','q8_0','--batch-size','512','--ubatch-size','256','--cache-ram','0')
$hardware=& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
[ordered]@{settings=$settings;gpu=$hardware;server=$exe}|ConvertTo-Json|Set-Content -Encoding utf8 -LiteralPath (Join-Path $PSScriptRoot 'native-launch.json')
& $exe @settings 1> (Join-Path $private 'llama.stdout') 2> (Join-Path $private 'llama.stderr')
