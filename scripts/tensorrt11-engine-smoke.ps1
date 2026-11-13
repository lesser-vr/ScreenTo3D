[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $repoRoot 'out\tensorrt11-smoke'
$pythonDependencies = Join-Path $repoRoot 'out\python-deps'
$modelPath = Join-Path $outputRoot 'fp16-identity.onnx'
$enginePath = Join-Path $outputRoot 'fp16-identity.plan'
$buildPath = Join-Path $outputRoot 'build'

$tensorRt = powershell -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $PSScriptRoot 'tensorrt-check.ps1') | ConvertFrom-Json
if (-not $tensorRt.available) { throw 'TensorRT validation failed.' }
if (-not $env:CUDA_PATH -or -not (Test-Path $env:CUDA_PATH)) {
    throw 'CUDA_PATH does not resolve to an installed CUDA Toolkit.'
}
if (-not (Test-Path (Join-Path $pythonDependencies 'onnx'))) {
    throw "Install ONNX with: python -m pip install --target `"$pythonDependencies`" onnx==1.20.0"
}

$env:TensorRT_PATH = $tensorRt.bin
$env:Path = "$($tensorRt.bin);$env:Path"
$env:PYTHONPATH = $pythonDependencies

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsPath = & $vswhere -latest -products * `
    -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw 'Visual Studio C++ tools were not found.' }
$devShell = Join-Path $vsPath 'Common7\Tools\Launch-VsDevShell.ps1'
$cmake = Join-Path $vsPath 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
$ninjaDirectory = Join-Path $vsPath 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja'
& $devShell -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$env:Path = "$ninjaDirectory;$env:Path"

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
python (Join-Path $repoRoot 'tools\tensorrt11-smoke\generate_fp16_identity_onnx.py') $modelPath
if ($LASTEXITCODE -ne 0) { throw 'FP16 ONNX fixture generation failed.' }

& $cmake -S (Join-Path $repoRoot 'tools\tensorrt11-smoke') -B $buildPath -G Ninja `
    -DCMAKE_BUILD_TYPE=Release `
    "-DSCREENTO3D_TENSORRT_ROOT=$($tensorRt.root)" `
    "-DSCREENTO3D_CUDA_ROOT=$env:CUDA_PATH"
if ($LASTEXITCODE -ne 0) { throw 'TensorRT 11 smoke configure failed.' }
& $cmake --build $buildPath
if ($LASTEXITCODE -ne 0) { throw 'TensorRT 11 smoke build failed.' }

$executable = Join-Path $buildPath 'screento3d_tensorrt11_smoke.exe'
$result = & $executable $modelPath $enginePath
if ($LASTEXITCODE -ne 0) { throw 'TensorRT 11 engine smoke failed.' }
$parsed = $result | ConvertFrom-Json
if (-not $parsed.fp16_io -or -not $parsed.deserialization_validated -or
    -not $parsed.atomic_publication) {
    throw 'TensorRT 11 smoke result failed validation.'
}

$result
