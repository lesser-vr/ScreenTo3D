param(
    [string]$InputVideo,
    [string]$OutputVideo,
    [ValidateSet('balanced', 'video-quality', 'offline-quality')]
    [string]$Mode = 'video-quality',
    [ValidateSet('h264', 'hevc')][string]$OutputCodec = 'h264',
    [string]$EngineDirectory,
    [string]$RuntimeDirectory = 'C:\TensorRT\TensorRT-11.2.1.2\bin',
    [switch]$Diagnostics,
    [switch]$LetterboxRefinement
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo 'out/vda-oracle-env/Scripts/python.exe'
$media = Join-Path $repo 'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg'
if (-not $EngineDirectory) { $EngineDirectory = Join-Path $repo 'out/vda-local' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Prepare the local VDA environment first; see docs/product-specs/vda-local-preview.md.' }
if ([bool]$InputVideo -ne [bool]$OutputVideo) { throw 'InputVideo and OutputVideo must be supplied together.' }
if ($Diagnostics -and $InputVideo) { throw 'Diagnostics cannot be combined with conversion.' }
$arguments = @('-m', 'depthsbs_app.main', '--depth-backend', 'vda-small',
    '--vda-engine-dir', $EngineDirectory, '--runtime-dir', $RuntimeDirectory,
    '--media-tools', $media, '--mode', $Mode, '--output-codec', $OutputCodec)
if ($Diagnostics) { $arguments += '--diagnostics' }
if ($LetterboxRefinement) { $arguments += '--letterbox-refinement' }
if ($InputVideo) { $arguments += @('--worker', '--input', $InputVideo, '--output', $OutputVideo) }
$priorPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repo 'v1'
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "VDA exited with code $LASTEXITCODE" }
} finally { $env:PYTHONPATH = $priorPythonPath }
