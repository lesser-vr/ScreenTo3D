[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'test-process-tree-memory.ps1')
$repoRoot = Split-Path -Parent $PSScriptRoot
$dependencies = Join-Path $repoRoot 'out\v1-python-deps'
if (-not (Test-Path $dependencies)) { throw 'V1 Python dependencies are missing.' }
$tensorRtBin = [Environment]::GetEnvironmentVariable('TensorRT_PATH', 'Machine')
if (-not $tensorRtBin -or -not (Test-Path (Join-Path $tensorRtBin 'nvinfer_11.dll'))) {
    $tensorRtBin = 'C:\TensorRT\TensorRT-11.2.1.2\bin'
}
if (-not (Test-Path (Join-Path $tensorRtBin 'nvinfer_11.dll'))) {
    throw 'TensorRT 11 runtime was not found for development tests.'
}
$env:Path = "$tensorRtBin;$env:Path"
$env:PYTHONPATH = "$dependencies;$(Join-Path $repoRoot 'v1')"
python -m unittest discover -s (Join-Path $repoRoot 'v1\tests') -v
if ($LASTEXITCODE -ne 0) { throw 'V1 Python tests failed.' }
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'dev.ps1')
if ($LASTEXITCODE -ne 0) { throw 'C++ regression tests failed.' }
