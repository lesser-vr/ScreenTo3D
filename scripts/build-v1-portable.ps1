[CmdletBinding()]
param([switch]$GpuPreview)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$dependencies = Join-Path $repoRoot 'out\v1-python-deps'
$model = Join-Path $repoRoot 'out\models\da2-small\model_fp16.onnx'
$tensorRtRoot = 'C:\TensorRT\TensorRT-11.2.1.2'
$tensorRtWheel = Join-Path $tensorRtRoot 'python\tensorrt-11.2.1.2-cp313-none-win_amd64.whl'
$ffmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
$ffprobe = (Get-Command ffprobe.exe -ErrorAction Stop).Source
$distRoot = Join-Path $repoRoot 'out\release'
$workRoot = Join-Path $repoRoot 'out\pyinstaller'
$appName = 'DepthSBS'
$entryPoint = Join-Path $repoRoot 'v1\depthsbs.py'
if ($GpuPreview) {
    $distRoot = Join-Path $repoRoot 'out\gpu-preview'
    $workRoot = Join-Path $repoRoot 'out\pyinstaller-gpu-preview'
    $appName = 'DepthSBS-GPU-Preview'
    $entryPoint = Join-Path $repoRoot 'v1\depthsbs_gpu_preview.py'
    & (Join-Path $PSScriptRoot 'build-cuda-projection-spike.ps1') -GpuPreview
}

if (-not (Test-Path (Join-Path $dependencies 'PyInstaller'))) {
    throw 'Install V1 dependencies into out\v1-python-deps first.'
}
if (-not (Test-Path (Join-Path $dependencies 'tensorrt'))) {
    python -m pip install --target $dependencies $tensorRtWheel
    if ($LASTEXITCODE -ne 0) { throw 'TensorRT Python binding install failed.' }
}
if (-not (Test-Path $model)) { throw 'Pinned DA2 Small FP16 ONNX is missing.' }

$env:PYTHONPATH = $dependencies
$env:Path = "$(Join-Path $tensorRtRoot 'bin');$env:Path"
$arguments = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed'
    '--name', $appName
    '--paths', (Join-Path $repoRoot 'v1')
    '--paths', $dependencies
    '--distpath', $distRoot
    '--workpath', $workRoot
    '--specpath', $workRoot
    '--collect-all', 'tensorrt'
    '--collect-submodules', 'cuda.bindings'
    '--add-data', "$model;models\da2-small"
    '--add-binary', "$ffmpeg;ffmpeg"
    '--add-binary', "$ffprobe;ffmpeg"
)
Get-ChildItem (Join-Path $tensorRtRoot 'bin') -Filter '*.dll' | ForEach-Object {
    $arguments += @('--add-binary', "$($_.FullName);runtime")
}
if ($GpuPreview) {
    $arguments += @('--add-binary', "$(Join-Path $repoRoot 'out/cuda-projection-preview/projection.dll');projection")
}
$arguments += $entryPoint

python @arguments
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller V1 build failed.' }
$portable = Join-Path $distRoot $appName
Copy-Item (Join-Path $repoRoot 'distribution\README.txt') $portable -Force
Copy-Item (Join-Path $repoRoot 'distribution\THIRD_PARTY_NOTICES.txt') $portable -Force
if ($GpuPreview) {
    Copy-Item (Join-Path $repoRoot 'distribution/GPU-PREVIEW.txt') $portable
    Copy-Item (Join-Path $repoRoot 'out/cuda-projection-preview/build-manifest.json') (Join-Path $portable 'projection-build-manifest.json')
    $cudaLicense = Join-Path (Split-Path (Split-Path (Get-Command nvcc).Source -Parent) -Parent) 'EULA.txt'
    Copy-Item $cudaLicense (Join-Path $portable 'CUDA-EULA.txt')
}
$license = Get-ChildItem $dependencies -Directory -Filter 'tensorrt-*.dist-info' | `
    ForEach-Object { Join-Path $_.FullName 'LICENSE.txt' } | `
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $license) { throw 'TensorRT license file was not found.' }
Copy-Item $license (Join-Path $portable 'TENSORRT-LICENSE.txt') -Force

$manifest = [ordered]@{
    schema_version = 1
    product_version = '1.0.0-rc1'
    gpu_preview = [bool]$GpuPreview
    model_sha256 = (Get-FileHash $model -Algorithm SHA256).Hash.ToLowerInvariant()
    tensorrt_version = '11.2.1.2'
    ffmpeg = (& $ffmpeg -version | Select-Object -First 1)
    built_at_utc = [DateTime]::UtcNow.ToString('o')
}
$manifest | ConvertTo-Json | Set-Content (Join-Path $portable 'build-manifest.json') -Encoding UTF8
Write-Output $portable
