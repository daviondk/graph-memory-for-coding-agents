param(
    [string]$Stage = 'D:/CodexResearch/x20-swe-context',
    [string]$Distribution = 'CodexX20MSR'
)
$ErrorActionPreference = 'Stop'
$base = Join-Path $Stage 'ollama-cpu'
$bin = Join-Path $base 'bin/ollama.exe'
$describe = Join-Path $base 'staging.json'
if (!(Test-Path -LiteralPath $describe) -or !(Test-Path -LiteralPath $bin)) {
    throw 'CPU Ollama has not been staged and verified'
}
if (Get-NetTCPConnection -LocalPort 18842 -State Listen -ErrorAction SilentlyContinue) {
    throw 'The dedicated Ollama port is already in use'
}
$env:OLLAMA_MODELS = Join-Path $base 'models'
$env:OLLAMA_HOST = '127.0.0.1:18842'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:GGML_VK_VISIBLE_DEVICES = '-1'
$env:ROCR_VISIBLE_DEVICES = '-1'
$env:OLLAMA_VULKAN = '0'
$env:OMP_NUM_THREADS = '2'
$env:GOMAXPROCS = '2'
$env:TEMP = Join-Path $base 'tmp'
$env:TMP = $env:TEMP
$profileDir = Join-Path $base 'isolated-profile'
[void](New-Item -ItemType Directory -Path $env:TEMP,$profileDir -Force)
$env:USERPROFILE = $profileDir
$o = Start-Process -FilePath $bin -ArgumentList 'serve' -WindowStyle Hidden -PassThru -WorkingDirectory $base -RedirectStandardError (Join-Path $base 'serve.stderr.log') -RedirectStandardOutput (Join-Path $base 'serve.stdout.log')
try {
    $o.ProcessorAffinity = [intptr]3
    $o.PriorityClass = 'BelowNormal'
    $ready = $false
    for ($try = 0; $try -lt 30; $try++) {
        if ($o.HasExited) { throw 'CPU Ollama exited at startup. See serve.stderr.log' }
        try {
            $version = Invoke-RestMethod 'http://127.0.0.1:18842/api/version' -TimeoutSec 2
            if ($version.version -eq '0.40.5') { $ready = $true; break }
        } catch { Start-Sleep -Seconds 1 }
    }
    if (!$ready) { throw 'The pinned Ollama API did not become ready' }
    function As-WslPath([string]$p) {
        $full = ([System.IO.Path]::GetFullPath($p)).Replace('\','/')
        return "/mnt/" + $full.Substring(0,1).ToLower() + $full.Substring(2)
    }
    $stageLinux = As-WslPath $Stage
    $reportPhysical = (Get-Item -LiteralPath $PSScriptRoot).FullName
    $scriptLinux = As-WslPath (Join-Path $reportPhysical 'recall_hybrid.py')
    $pkg = "$stageLinux/apk-recall/usr/lib"
    $work = Start-Process -FilePath 'wsl.exe' -ArgumentList (@('-d',$Distribution,'-u','root','--','env',
        "PYTHONPATH=$pkg/python3.12/site-packages","LD_LIBRARY_PATH=$pkg",'OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
        'python3','-u',$scriptLinux,'--data',$stageLinux,'--upstream',"$stageLinux/recall-upstream")) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $base 'run.stdout.log') -RedirectStandardError (Join-Path $base 'run.stderr.log')
    $attested = $false
    while (!$work.WaitForExit(2000)) {
        $psInfo = Invoke-RestMethod 'http://127.0.0.1:18842/api/ps' -TimeoutSec 3
        if ($psInfo.models.Count -and !$attested) {
            $m = $psInfo.models[0]
            if ([int64]$m.size_vram -ne 0) { throw 'The embedding runtime reports GPU memory use' }
            $evidence = [ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o'); server_pid=$o.Id; affinity=$o.ProcessorAffinity.ToInt64();
                max_loaded=1; parallel=1; version=$version.version; ps=$psInfo; gpu_query=(nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader | Out-String)}
            $evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'recall_cpu_backend.json') -Encoding UTF8
            $attested = $true
        }
    }
    if ($work.ExitCode -ne 0) { throw 'The original Recall hybrid driver failed. See run.stderr.log' }
    if (!$attested) { throw 'Missing CPU backend attestation' }
} finally {
    if (!$o.HasExited) {
        try { Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18842/api/generate' -ContentType 'application/json' -Body '{"model":"nomic-embed-text","keep_alive":0}' -TimeoutSec 15 | Out-Null } catch { }
        $o.Kill()
        $o.WaitForExit(10000) | Out-Null
    }
    Get-Process -Name ollama -ErrorAction SilentlyContinue | Where-Object Path -EQ $bin.Replace('/','\') | ForEach-Object { Stop-Process -Id $_.Id -Force }
}
