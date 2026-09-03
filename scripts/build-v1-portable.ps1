[CmdletBinding()]
param()

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
    '--name', 'DepthSBS'
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
$arguments += (Join-Path $repoRoot 'v1\depthsbs.py')

python @arguments
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller V1 build failed.' }
$portable = Join-Path $distRoot 'DepthSBS'
Copy-Item (Join-Path $repoRoot 'distribution\README.txt') $portable -Force
Copy-Item (Join-Path $repoRoot 'distribution\THIRD_PARTY_NOTICES.txt') $portable -Force
$license = Get-ChildItem $dependencies -Directory -Filter 'tensorrt-*.dist-info' | `
    ForEach-Object { Join-Path $_.FullName 'LICENSE.txt' } | `
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $license) { throw 'TensorRT license file was not found.' }
Copy-Item $license (Join-Path $portable 'TENSORRT-LICENSE.txt') -Force

$manifest = [ordered]@{
    schema_version = 1
    product_version = '1.0.0-rc1'
    model_sha256 = (Get-FileHash $model -Algorithm SHA256).Hash.ToLowerInvariant()
    tensorrt_version = '11.2.1.2'
    ffmpeg = (& $ffmpeg -version | Select-Object -First 1)
    built_at_utc = [DateTime]::UtcNow.ToString('o')
}
$manifest | ConvertTo-Json | Set-Content (Join-Path $portable 'build-manifest.json') -Encoding UTF8
Write-Output $portable
