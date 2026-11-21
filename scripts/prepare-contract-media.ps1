[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Destination)
$ErrorActionPreference = 'Stop'
# Test dependency only; this does not replace or bundle the application's FFmpeg.
# Pin the publisher versioned GitHub release and its archive checksum.
$contractRoot = [System.IO.Path]::GetFullPath($Destination)
$contractArchive = Join-Path $contractRoot 'ffmpeg-8.1.2.zip'
$contractHash = 'db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec'
New-Item -ItemType Directory -Path $contractRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $contractArchive)) {
    Invoke-WebRequest -Uri 'https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-essentials_build.zip' -OutFile $contractArchive
}
if ((Get-FileHash -LiteralPath $contractArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $contractHash) {
    throw 'Contract media package checksum mismatch; refusing extraction.'
}
$contractBin = Join-Path $contractRoot 'ffmpeg-8.1.2-essentials_build/bin'
if (-not (Test-Path -LiteralPath $contractBin)) {
    Expand-Archive -LiteralPath $contractArchive -DestinationPath $contractRoot
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$contractZip = [System.IO.Compression.ZipFile]::OpenRead($contractArchive)
try {
foreach ($contractTool in @('ffmpeg.exe','ffprobe.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $contractBin $contractTool))) { throw "Missing $contractTool" }
    $contractEntry = $contractZip.GetEntry("ffmpeg-8.1.2-essentials_build/bin/$contractTool")
    if ($null -eq $contractEntry) { throw 'Archive tool entry is missing' }
    $contractStream = $contractEntry.Open()
    $contractHasher = [System.Security.Cryptography.SHA256]::Create()
    try { $contractExpected = [BitConverter]::ToString($contractHasher.ComputeHash($contractStream)).Replace('-', '') }
    finally { $contractStream.Dispose(); $contractHasher.Dispose() }
    if ((Get-FileHash -LiteralPath (Join-Path $contractBin $contractTool)).Hash -ne $contractExpected) {
        throw 'Extracted media tool changed; refusing reuse.'
    }
}
} finally { $contractZip.Dispose() }
Write-Output $contractBin
