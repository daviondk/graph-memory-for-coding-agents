$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$py='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$env:RAYON_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
function Run-Step([string]$file,[string[]]$params){
    & $py -B -u (Join-Path $root $file) @params
    if($LASTEXITCODE){throw "$file $params exited $LASTEXITCODE"}
}
while (!(Test-Path -LiteralPath "$root/residual_graph/cost-ft.json")) {Start-Sleep -Seconds 15}
Run-Step 'fine_train/apply.py' @('fit')
foreach ($mode in @('dev','dense')){
    Run-Step 'fine_train/apply.py' @($mode)
    Run-Step 'assess.py' @('fine_train',$mode)
}
Run-Step 'render_audit.py' @('predict','fine_train','dense')
Run-Step 'render_audit.py' @('score','fine_train','dense')
while (!(Test-Path -LiteralPath "$root/residual_graph/forecast-seal.json")) {Start-Sleep -Seconds 15}
foreach ($folder in @('fine_read','fine_train')){
    if ($folder -eq 'fine_train') {Run-Step 'fine_train/apply.py' @('rgcn')} else {Run-Step 'fine_read/reader.py' @('rgcn')}
    Run-Step 'assess.py' @($folder,'rgcn')
}
Run-Step 'render_audit.py' @('predict','fine_train','rgcn')
Run-Step 'render_audit.py' @('score','fine_train','rgcn')
