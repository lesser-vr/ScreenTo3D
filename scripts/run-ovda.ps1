param(
    [string]$InputVideo,
    [string]$OutputVideo,
    [ValidateSet('video-quality')]
    [string]$Mode = 'video-quality',
    [ValidateSet('h264', 'hevc')][string]$OutputCodec = 'h264',
    [ValidateSet('cpu', 'cuda')][string]$StereoRenderer = 'cuda',
    [string]$EngineDirectory,
    [string]$RuntimeDirectory = 'C:\TensorRT\TensorRT-11.2.1.2\bin',
    [switch]$Diagnostics,
    [switch]$CheckInstallation,
    [switch]$NonCommercial,
    [switch]$LetterboxRefinement
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo 'out/vda-oracle-env/Scripts/python.exe'
$sitePackages = Join-Path $repo 'out/vda-oracle-env/Lib/site-packages'
$media = Join-Path $repo 'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg'
if (-not $EngineDirectory) { $EngineDirectory = Join-Path $repo 'out/ovda-local' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Prepare oVDA first: docs/product-specs/ovda-local-preview.md' }
if (-not (Test-Path -LiteralPath $sitePackages)) { throw 'Prepared oVDA packages are missing.' }
$configuration = Join-Path $repo 'out/vda-oracle-env/pyvenv.cfg'
$configuredHome = if (Test-Path -LiteralPath $configuration) {
    (Get-Content -LiteralPath $configuration | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1) -replace '^home\s*=\s*', ''
}
if (-not $configuredHome -or $configuredHome -like '*\WindowsApps\*' -or
        -not (Test-Path -LiteralPath (Join-Path $configuredHome 'python.exe'))) {
    $uvPythonRoot = Join-Path $env:APPDATA 'uv/python'
    $python = Get-ChildItem -LiteralPath $uvPythonRoot -Directory -Filter 'cpython-3.13.*-windows-x86_64-none' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object { Join-Path $_.FullName 'python.exe' } |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if (-not $python) {
        throw 'Unable to resolve a compatible Python 3.13 runtime for the prepared oVDA packages.'
    }
}
if ([bool]$InputVideo -ne [bool]$OutputVideo) { throw 'InputVideo and OutputVideo must be supplied together.' }
if ($Diagnostics -and $InputVideo) { throw 'Diagnostics cannot be combined with conversion.' }
if ($CheckInstallation -and ($Diagnostics -or $InputVideo)) { throw 'CheckInstallation cannot be combined with diagnostics/conversion.' }
if (($Diagnostics -or $InputVideo) -and -not $NonCommercial) { throw 'Read experiments/ovda/LICENSE and specify -NonCommercial for personal/non-commercial use.' }
$arguments = @('-m', 'screento3d_app.main', '--depth-backend', 'ovda-small-c16',
    '--ovda-engine-dir', $EngineDirectory, '--runtime-dir', $RuntimeDirectory,
    '--media-tools', $media, '--mode', $Mode, '--output-codec', $OutputCodec, '--stereo-renderer', $StereoRenderer)
if ($Diagnostics) { $arguments += '--diagnostics' }
if ($CheckInstallation) { $arguments += '--check-installation' }
if ($NonCommercial) { $arguments += '--ovda-noncommercial' }
if ($LetterboxRefinement) { $arguments += '--letterbox-refinement' }
if ($InputVideo) { $arguments += @('--worker', '--input', $InputVideo, '--output', $OutputVideo) }
$priorPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = (@('v1', 'out/vda-oracle-env/Lib/site-packages', 'out/v1-python-deps') |
        ForEach-Object { Join-Path $repo $_ }) -join ';'
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "oVDA exited with code $LASTEXITCODE" }
} finally { $env:PYTHONPATH = $priorPythonPath }
