# Phase-specific continuation after all five embedding caches have been sealed.
$ErrorActionPreference='Stop'
$work=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$canon=Join-Path $work 'graph_memory_round22/native_multiseed/official580'
$private='D:/CodexResearch/x20-native-multiseed/official580'
$runtime='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='1'
$env:PYTHONUTF8='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:TEMP='D:/CodexResearch/x20-native-multiseed/tmp'
$env:TMP=$env:TEMP
foreach ($seed in 13,17,29,37,41) {
    if (!(Test-Path -LiteralPath "$canon/seed-$seed/embeddings.json")) {throw 'Expected complete five-seed embedding cache'}
}
foreach($key in 'train','dev','test') {
    if (!(Test-Path -LiteralPath "$private/scratch/$key-features.fp32")) {throw "Missing existing scratch $key"}
}
$locks=@()
try {
    foreach ($name in 'Local\CodexResearchNativeGraph580Queue','Local\CodexResearchGraphMemoryFiveSeed') {
        $lock=[Threading.Mutex]::new($false,$name)
        try {$ok=$lock.WaitOne(0)} catch [Threading.AbandonedMutexException] {$ok=$true}
        if (!$ok) {$lock.Dispose();throw 'Another native worker holds the shared mutex'}
        $locks+=$lock
    }
    & $runtime -B -c 'import torch; x=torch.arange(4,device="cuda"); assert x.sum().item()==6'
    if ($LASTEXITCODE -ne 0) {throw 'CUDA qualification failed'}
    foreach ($stage in 'fit','rank','score','aggregate') {
        $receipt=@{fit='seed-41/wo_chunk_adjacency/fit.json';rank='seed-41/wo_chunk_adjacency/forecast-seal.json';score='seed-41/wo_chunk_adjacency/results.json';aggregate='five-seed-results.json'}[$stage]
        if (Test-Path -LiteralPath "$canon/$receipt") {continue}
        if ((Get-PSDrive D).Free -lt 2GB) {throw 'Insufficient free space for this stage'}
        $argsList=@('-B','-u',"$canon/official.py",$stage)
        if ($stage -ne 'aggregate') {$argsList+=@('41','wo_chunk_adjacency')}
        $tag="r39-last-$stage-"+[DateTime]::UtcNow.Ticks
        $p=Start-Process -WindowStyle Hidden -FilePath $runtime -ArgumentList $argsList -PassThru -RedirectStandardOutput "$private/logs/$tag.log" -RedirectStandardError "$private/logs/$tag.err"
        $hot=0;$deadline=[datetime]::UtcNow.AddHours(2)
        try {
            while (!$p.WaitForExit(10000)) {
                $temperature=[int](@(& nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits)[0])
                if ($temperature -ge 89) {$hot++} else {$hot=0}
                if ($hot -ge 2 -or (Get-PSDrive D).Free -lt 2GB -or [datetime]::UtcNow -gt $deadline) {throw 'Last-stage resource bound'}
            }
            $p.Refresh()
            if ($p.ExitCode -ne 0 -or !(Test-Path -LiteralPath "$canon/$receipt")) {throw "Unfinished $stage; see $tag"}
        } finally {if (!$p.HasExited) {$p.Kill($true);$p.WaitForExit()};$p.Dispose()}
        Write-Output "Confirmed $receipt"
    }
} finally {
    foreach ($lock in $locks) {$lock.ReleaseMutex();$lock.Dispose()}
}
