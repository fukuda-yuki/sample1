$ErrorActionPreference = 'Stop'
$reportRoot = $PSScriptRoot
$credential = [Environment]::GetEnvironmentVariable('OPENCODE_GO_API_KEY', 'User')
if ([string]::IsNullOrWhiteSpace($credential)) { throw 'Configured user gateway credential is unavailable for the exact-value check.' }
$paths = @(Get-ChildItem -LiteralPath $reportRoot -Recurse -File)
$bytesScanned = 0L
foreach ($artifact in $paths) {
    $artifactBytes = [IO.File]::ReadAllBytes($artifact.FullName)
    $bytesScanned += $artifactBytes.LongLength
    if ([Text.Encoding]::UTF8.GetString($artifactBytes).Contains($credential)) {
        throw ('Credential found in report artifact: ' + $artifact.FullName)
    }
}
$proof = [ordered]@{
    exact_gateway_credential_absent = $true
    files_scanned = $paths.Count
    bytes_scanned = $bytesScanned
    credential_value_or_hash_disclosed = $false
    environment_changed = $false
    temporary_secret_file_created = $false
    scope = 'v3 report folder only; existing originals were not changed'
}
$credential = $null
$proof | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $reportRoot 'checks/secret-scan.json') -Encoding utf8
$proof | ConvertTo-Json -Compress
