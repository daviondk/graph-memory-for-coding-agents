$ErrorActionPreference='Stop'
$dir='D:/CodexResearch/x20-r27-code-data'
$locDir='D:/CodexResearch/x20-r8-swerank-runtime'
foreach ($p in @($dir,$locDir)){New-Item -ItemType Directory -Path $p -Force | Out-Null}
$urls=@(
  @('https://huggingface.co/datasets/SWE-Explore-Bench/SWE-Explore-Bench/resolve/bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9/bench.final.public.jsonl',(Join-Path $dir 'swe-explore.jsonl'),'dc4f114ececd0bfb987361c26ae5e2440456e2cccb36adfccb09ea5385aec202'),
  @('https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/resolve/c104f840cc67f8b6eec6f759ebc8b2693d585d4a/data/test-00000-of-00001.parquet',(Join-Path $dir 'verified.parquet'),'a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd'),
  @('https://huggingface.co/datasets/czlll/Loc-Bench_V1/resolve/c44cf3b74e07ca642cec841b471a9939907c12a7/data/test-00000-of-00001.parquet',(Join-Path $locDir 'locbench-test-c44cf3b74e07ca642cec841b471a9939907c12a7.parquet'),'8df0833c2c1276c5837aab923d489ab97d7654529abe759d0f59242c4978a662')
)
foreach ($a in $urls) {
  if (-not (Test-Path -LiteralPath $a[1])) {curl.exe -LfSs $a[0] -o $a[1]; if($LASTEXITCODE -ne 0){throw 'Download failed'}}
  if ((Get-FileHash -LiteralPath $a[1]).Hash -ne $a[2]) {throw "Source integrity mismatch in $($a[1])"}
}
