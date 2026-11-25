$ErrorActionPreference='Stop'
$s=$PSScriptRoot
$r='D:/CodexResearch/x20-isetrace-residual/logs'
$py='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:RAYON_NUM_THREADS='2'
foreach($panel in @('availability','hash64')){
    if ($panel -eq 'availability'){
        while (!(Test-Path "$s/$panel/cpu-encoding.json")){
            if (!(Get-CimInstance Win32_Process -Filter "Name='python.exe'"|Where-Object {$_.CommandLine -match 'fallback.py.+encode.+availability'})){throw 'Early fallback encoder stopped'}
            Start-Sleep -Seconds 5
        }
    } else {
        & $py -B -u "$s/fallback.py" encode $panel
        if($LASTEXITCODE){throw 'Hash panel encoding failed'}
    }
    & $py -B -u "$s/fallback.py" train $panel
    if($LASTEXITCODE){throw "CPU training failed at $panel"}
    & $py -B -u "$s/read.py" rank $panel
    if($LASTEXITCODE){throw "CPU ranks failed at $panel"}
    & $py -B -u "$s/read.py" score $panel
    if($LASTEXITCODE){throw "CPU score failed at $panel"}
}

