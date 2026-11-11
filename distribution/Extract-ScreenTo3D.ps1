param([string]$Destination = '')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
function Get-Sha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try { return [System.BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'release-manifest.json') -Raw | ConvertFrom-Json
if ($manifest.product_version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid release version.' }
if (-not $Destination) { $Destination = Join-Path $PSScriptRoot "ScreenTo3D-$($manifest.product_version)-bundle" }
$targetRoot = [System.IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $targetRoot) { throw 'Choose a new destination folder; existing files will not be replaced.' }
foreach ($asset in $manifest.assets) {
    $validRoot = if ($asset.kind -eq 'application') { "ScreenTo3D-$($manifest.product_version)" } elseif ($asset.kind -eq 'optional-models') { 'packs' } else { throw 'Unknown archive kind.' }
    if ($asset.root -cne $validRoot -or [System.IO.Path]::GetFileName($asset.name) -cne $asset.name -or $asset.name -notlike '*.zip') { throw 'Invalid archive root or filename.' }
}
$archives = @($manifest.assets | Where-Object { $_.kind -eq 'application' -or (Test-Path -LiteralPath (Join-Path $PSScriptRoot $_.name)) })
if (-not @($archives | Where-Object kind -eq 'application').Count) { throw 'No application archives were listed.' }
$seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($asset in $archives) {
    if ([System.IO.Path]::GetFileName($asset.name) -cne $asset.name -or $asset.sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid asset manifest.' }
    $path = Join-Path $PSScriptRoot $asset.name
    if (-not (Test-Path -LiteralPath $path)) { throw "Download all application ZIPs first: $($asset.name)" }
    Write-Host "Verifying $($asset.name)..."
    if ((Get-Item -LiteralPath $path).Length -ne $asset.bytes -or (Get-Sha256 $path) -cne $asset.sha256) { throw "Checksum mismatch: $($asset.name)" }
    $zip = [System.IO.Compression.ZipFile]::OpenRead($path)
    try {
        foreach ($entry in $zip.Entries) {
            $relative = $entry.FullName.Replace('/', '\')
            $resolved = [System.IO.Path]::GetFullPath((Join-Path $targetRoot $relative))
            $expected = [System.IO.Path]::GetFullPath((Join-Path $targetRoot $asset.root)) + '\'
            if (-not $resolved.StartsWith($expected, [System.StringComparison]::OrdinalIgnoreCase) -or -not $seen.Add($resolved)) { throw 'Archive contains an unsafe or duplicate destination.' }
        }
    } finally { $zip.Dispose() }
}
New-Item -ItemType Directory -Path $targetRoot | Out-Null
foreach ($asset in $archives) {
    Write-Host "Extracting $($asset.name)..."
    [System.IO.Compression.ZipFile]::ExtractToDirectory((Join-Path $PSScriptRoot $asset.name), $targetRoot)
}
Write-Host "Ready: $targetRoot\ScreenTo3D-$($manifest.product_version)\ScreenTo3D.exe"
