$ErrorActionPreference='Stop'
$root=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath=& $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$sdk=Join-Path $root 'out/vfg-sdk-1.3.0.0/VideoFX'
$build=Join-Path $root 'out/vfg-native-bridge-detail'
New-Item -ItemType Directory -Path $build -Force | Out-Null
Push-Location $build
try {
  & nvcc -shared -O2 --fmad=false -arch=sm_120 -std=c++17 -Xcompiler /MD -Xcompiler /utf-8 `
    -I "$sdk/nvvfx/include" -I "$sdk/features/nvvfxvideoframegeneration/include" `
    "$root/experiments/vfg/native_bridge.cu" "$sdk/nvvfx/src/nvVideoEffectsProxy.cpp" "$sdk/nvvfx/src/nvCVImageProxy.cpp" `
    -o vfg_native_bridge.dll -ld3d11 -ldxgi
  if($LASTEXITCODE -ne 0){throw 'VFG bridge build failed'}
  [ordered]@{source_sha256=(Get-FileHash "$root/experiments/vfg/native_bridge.cu").Hash;
    detail_source_sha256=(Get-FileHash "$root/experiments/cuda_projection/stereo_detail.cuh").Hash;
    layout_source_sha256=(Get-FileHash "$root/experiments/cuda_projection/live_depth.cu").Hash;
    dll_sha256=(Get-FileHash vfg_native_bridge.dll).Hash;nvcc=(& nvcc --version | Out-String)} |
    ConvertTo-Json | Set-Content build-manifest.json
} finally {Pop-Location}
