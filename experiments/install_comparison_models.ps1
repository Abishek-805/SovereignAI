$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$manifestPath=Join-Path $projectRoot 'benchmarks/model-comparison/install-manifest.json'
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
function Get-ComparisonHash([string]$path) {
    $stream=[IO.File]::OpenRead($path)
    $hasher=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $hasher.Dispose() }
}
try {
    foreach($candidate in $manifest.models) {
        $target=Join-Path $projectRoot $candidate.path
        $partial=$target+'.part'
        $url='https://huggingface.co/'+$candidate.repository+'/resolve/'+$candidate.revision+'/'+[IO.Path]::GetFileName($target)+'?download=true'
        if (!(Test-Path -LiteralPath $target)) {
            for($attempt=1;$attempt -le 20;$attempt++) {
                & curl.exe --fail --location --http1.1 --continue-at - --max-time 120 --speed-limit 1024 --speed-time 30 --silent --show-error --output $partial $url
                if ((Test-Path -LiteralPath $partial) -and (Get-Item -LiteralPath $partial).Length -eq $candidate.expected_bytes) {break}
                Write-Output ($candidate.id+' download attempt '+$attempt+' incomplete')
            }
            if (!(Test-Path -LiteralPath $partial) -or (Get-Item -LiteralPath $partial).Length -ne $candidate.expected_bytes) {throw ($candidate.id+' download incomplete')}
            if ((Get-ComparisonHash $partial) -ne $candidate.expected_sha256) {throw ($candidate.id+' SHA-256 mismatch')}
            Move-Item -LiteralPath $partial -Destination $target
        }
        if ((Get-Item -LiteralPath $target).Length -ne $candidate.expected_bytes -or (Get-ComparisonHash $target) -ne $candidate.expected_sha256) {throw ($candidate.id+' installed file does not match manifest')}
        $candidate | Add-Member -NotePropertyName download_verified -NotePropertyValue $true -Force
        $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding utf8
        Write-Output ($candidate.id+' verified')
    }
    $manifest.status='INSTALLED_COMPATIBILITY_PENDING'
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    & python experiments/model_compatibility.py
    if ($LASTEXITCODE -ne 0) {throw 'Compatibility harness blocked; inspect saved logs'}
    $manifest.status='COMPATIBILITY_RECORDED'
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding utf8
} catch {
    $manifest.status='BLOCKED'
    $manifest | Add-Member -NotePropertyName error -NotePropertyValue $_.Exception.Message -Force
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    Write-Error $_
    exit 1
}
