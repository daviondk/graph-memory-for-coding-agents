$ErrorActionPreference = 'Stop'
$repo = 'swerebenchv2/ipython-traitlets'
$token = (Invoke-RestMethod "https://auth.docker.io/token?service=registry.docker.io&scope=repository:${repo}:pull").token
$api = "https://registry-1.docker.io/v2/$repo"
$head = @{Authorization="Bearer $token"; Accept='application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'}
$r = Invoke-WebRequest "$api/manifests/670-191ff75" -Headers $head -UseBasicParsing
$m = $(if ($r.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($r.Content) } else { $r.Content }) | ConvertFrom-Json
if ($m.manifests) {
 $amd = $m.manifests | Where-Object { $_.platform.os -eq 'linux' -and $_.platform.architecture -eq 'amd64' } | Select-Object -First 1
 $r = Invoke-WebRequest "$api/manifests/$($amd.digest)" -Headers $head -UseBasicParsing
 $m = $(if ($r.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($r.Content) } else { $r.Content }) | ConvertFrom-Json
}
$measured=@()
foreach ($layer in $m.layers) {
  # gzip ISIZE is the original tar size modulo 2^32; together these are a lower bound.
  $client=[Net.Http.HttpClient]::new()
  try {
    $req=[Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Get, "$api/blobs/$($layer.digest)")
    $req.Headers.Authorization=[Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer',$token)
    $req.Headers.Range=[Net.Http.Headers.RangeHeaderValue]::new(([long]$layer.size-4),([long]$layer.size-1))
    $res=$client.SendAsync($req,[Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
    $length=$null
    if ([int]$res.StatusCode -eq 206 -and $res.Content.Headers.ContentLength -eq 4) {
      $buffer=$res.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
      $length=[BitConverter]::ToUInt32($buffer,0)
    }
    $measured += [ordered]@{digest=$layer.digest;compressed=$layer.size;unpacked_lower_bound=$length;range_status=[int]$res.StatusCode;media_type=$layer.mediaType}
    $res.Dispose()
  } finally {$client.Dispose()}
}
$summary=[ordered]@{compressed_bytes=($m.layers | Measure-Object size -Sum).Sum;manifest=($r.Headers['Docker-Content-Digest']|Select-Object -First 1);layers=$measured;unpacked_lower_bound=(($measured | ForEach-Object { $_.unpacked_lower_bound } | Measure-Object -Sum).Sum)}
$summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $PSScriptRoot 'image.json')
Write-Output "Compressed $($summary.compressed_bytes) / unpacked lower bound $($summary.unpacked_lower_bound)"
