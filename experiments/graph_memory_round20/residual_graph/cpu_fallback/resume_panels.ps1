$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$root=Split-Path -Parent $s
$py='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$cpu='D:/CodexResearch/x20-isetrace-runtime/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
if (Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {$_.CommandLine -match 'cpu_fallback[/\\](fallback.py|read.py|topology_hash.py)'}) {throw 'Existing panel worker owns the input caches and outputs; retain it'}
foreach($panel in @('availability','hash64')){
    if (Test-Path "$s/$panel/MANIFEST_SHA256.json"){
        & $cpu -B "$s/verify_panel.py" $panel
        if ($LASTEXITCODE){throw 'Stored panel verification failed'}
        continue
    }
    foreach($stage in @('encode','train')){
        $target=if($stage -eq 'encode'){'cpu-encoding.json'}else{'checkpoint.json'}
        if (!(Test-Path "$s/$panel/$target")){
            & $py -B -u "$s/fallback.py" $stage $panel
            if($LASTEXITCODE){throw "$panel $stage failed"}
        }
    }
    foreach($stage in @('rank','score')){
        $target=if($stage -eq 'rank'){'forecast-seal.json'}else{'results.json'}
        if (!(Test-Path "$s/$panel/$target")){
            & $py -B -u "$s/read.py" $stage $panel
            if($LASTEXITCODE){throw "$panel $stage failed"}
        }
    }
    if($panel -eq 'hash64' -and !(Test-Path "$s/hash64/topology-results.json")){
        if(!(Test-Path "$s/hash64/topology-seal.json")){
            & $py -B -u "$s/topology_hash.py" rank
            if($LASTEXITCODE){throw 'Structural intervention forecast failed'}
        }
        & $py -B -u "$s/topology_hash.py" score
        if($LASTEXITCODE){throw 'Structural intervention score failed'}
    }
    & $cpu -B -u "$s/finish_panel.py" $panel
    if($LASTEXITCODE){throw 'Panel manifest failed'}
}

