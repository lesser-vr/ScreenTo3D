param(
    [string]$InputVideo,
    [string]$OutputVideo,
    [ValidateSet('performance','balanced','video-quality','offline-quality')][string]$Mode = 'balanced',
    [ValidateSet('h264','hevc')][string]$OutputCodec = 'h264',
    [switch]$Diagnostics
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if ([bool]$InputVideo -ne [bool]$OutputVideo) { throw 'Supply both input and output.' }
if ($Diagnostics -and $InputVideo) { throw 'Diagnostics cannot be combined with conversion.' }
$arguments = @('-m','depthsbs_app.main','--depth-backend','da2-base',
    '--da2-base-engine-dir',(Join-Path $repo 'out/da2-base-local'),
    '--runtime-dir','C:/TensorRT/TensorRT-11.2.1.2/bin',
    '--media-tools',(Join-Path $repo 'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg'),
    '--mode',$Mode,'--output-codec',$OutputCodec)
if ($Diagnostics) { $arguments += '--diagnostics' }
if ($InputVideo) { $arguments += @('--worker','--input',$InputVideo,'--output',$OutputVideo) }
$priorPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repo 'v1'
    & (Join-Path $repo 'out/vda-oracle-env/Scripts/python.exe') @arguments
    if ($LASTEXITCODE -ne 0) { throw "DA2 Base exited with code $LASTEXITCODE" }
} finally { $env:PYTHONPATH = $priorPythonPath }
