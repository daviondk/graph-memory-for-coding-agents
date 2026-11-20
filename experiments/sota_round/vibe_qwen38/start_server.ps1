param([int]$TotalContext=49152,[int]$Slots=1)
$ErrorActionPreference="Stop"
$runRoot=$PSScriptRoot
$nativeBinary=Join-Path $runRoot "bin/llama-server.exe"
$modelFile=Join-Path $runRoot "Qwen3.8-27B-UD-Q4_K_M.gguf"
foreach($required in @("model_receipt.json","runtime_receipt.json")){
  if(!(Test-Path -LiteralPath (Join-Path $runRoot $required))){throw "Missing verified artifact receipt: $required"}
}
if(Get-NetTCPConnection -State Listen -LocalPort 18839,18840 -ErrorAction SilentlyContinue){throw "Requested local port already in use"}
$nativeArgs=@("-m",$modelFile,"--alias","qwen38-27b-ud-q4km","--host","127.0.0.1","--port","18840",
              "--jinja","--parallel","$Slots","--ctx-size","$TotalContext","--n-gpu-layers","all",
              "--flash-attn","on","--cache-type-k","q8_0","--cache-type-v","q8_0",
              "--batch-size","512","--ubatch-size","256","--cache-ram","0","--metrics")
$nativeOut=Join-Path $runRoot "native.stdout.log"
$nativeErr=Join-Path $runRoot "native.stderr.log"
$native=Start-Process -FilePath $nativeBinary -ArgumentList $nativeArgs -WindowStyle Hidden -WorkingDirectory (Join-Path $runRoot "bin") -RedirectStandardOutput $nativeOut -RedirectStandardError $nativeErr -PassThru
$proxyOut=Join-Path $runRoot "proxy.stdout.log"
$proxyErr=Join-Path $runRoot "proxy.stderr.log"
$proxyScript=Join-Path $runRoot "seed_proxy.py"
$proxyPy=(Get-Command python.exe).Source
$proxy=Start-Process -FilePath $proxyPy -ArgumentList @("-X","utf8",$proxyScript) -WorkingDirectory $runRoot -WindowStyle Hidden -RedirectStandardOutput $proxyOut -RedirectStandardError $proxyErr -PassThru
[pscustomobject]@{native_pid=$native.Id;proxy_pid=$proxy.Id;utc=[DateTime]::UtcNow.ToString("o");native_arguments=$nativeArgs;ports=@(18839,18840);scope="loopback-only";slots=$Slots;total_context=$TotalContext} | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $runRoot "service.json")
Get-Content -LiteralPath (Join-Path $runRoot "service.json")
