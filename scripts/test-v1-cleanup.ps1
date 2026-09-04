[CmdletBinding()]
param(
    [string]$SourcePath = 'out/media-smoke/fixture-720p30.mp4',
    [ValidateRange(1, 20)] [int]$Runs = 3
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$dependencies = Join-Path $repoRoot 'out/v1-python-deps'
$tensorRtBin = [Environment]::GetEnvironmentVariable('TensorRT_PATH', 'Machine')
if (-not $tensorRtBin -or -not (Test-Path (Join-Path $tensorRtBin 'nvinfer_11.dll'))) {
    $tensorRtBin = 'C:/TensorRT/TensorRT-11.2.1.2/bin'
}
if (-not (Test-Path (Join-Path $tensorRtBin 'nvinfer_11.dll'))) { throw 'TensorRT runtime missing.' }
$env:Path = "$tensorRtBin;$env:Path"
$env:PYTHONPATH = "$dependencies;$(Join-Path $repoRoot 'v1')"
python (Join-Path $repoRoot 'v1/cleanup_smoke.py') --input (Resolve-Path $SourcePath).Path --runs $Runs
if ($LASTEXITCODE -ne 0) { throw 'Repeated GPU cleanup smoke failed.' }
