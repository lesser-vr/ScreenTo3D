# Build from the same production sources/flags with native Blackwell code and
# forward-JIT PTX for Turing and newer CUDA devices.
param([string[]]$Only)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vs 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$dir = Join-Path $root 'out/portable-cuda'
$src = Join-Path $root 'experiments/cuda_projection'
$sdk = Join-Path $root 'out/vfg-sdk-1.3.0.0/VideoFX'
$common = @('-shared','-O2','--fmad=false','-gencode=arch=compute_75,code=compute_75','-gencode=arch=compute_120,code=sm_120','-std=c++17','-Xcompiler','/MD','-Xcompiler','/utf-8','-DDEPTHSBS_PORTABLE_CUDA=1')
function Build-Dll($name, $arguments) {
    if ($Only -and $name -notin $Only) { return }
    & nvcc @common @arguments -o "$name.dll"
    if ($LASTEXITCODE) { throw "CUDA build failed for $name" }
}
New-Item -Type Directory -Force $dir | Out-Null
Push-Location $dir
try {
    foreach ($name in 'live_depth','live_texture_runtime','small_input') {
        Build-Dll $name @("$src/$name.cu",'-DDEPTHSBS_FAST_GUIDE=1','-DDEPTHSBS_BITMAP_RESOLVE=1','-DDEPTHSBS_GUIDE_COMPENSATED=1','-DDEPTHSBS_FIXED_GUIDE_8=1','-ld3d11','-ldxgi')
    }
    Build-Dll 'base_input' @("$src/base_input.cu")
    Build-Dll 'flat_background' @("$src/flat_background.cu")
    Build-Dll 'vda_input' @("$src/base_input.cu",'-DDEPTHSBS_VDA_INPUT=1')
    Build-Dll 'projection' @("$src/projection.cu",'-DDEPTHSBS_GPU_PREVIEW=1')
    Build-Dll 'native_memory' @("$src/native_memory.cu")
    Build-Dll 'live_motion' @("$root/experiments/optical_flow/live_motion.cu",'-Xcompiler','/EHsc','-I',"$root/out/nvof-sdk-headers",'-lcuda','-Xlinker','/NODEFAULTLIB:LIBCMT')
    Build-Dll 'vfg_native_bridge' @("$root/experiments/vfg/native_bridge.cu",'-I',"$sdk/nvvfx/include",'-I',"$sdk/features/nvvfxvideoframegeneration/include","$sdk/nvvfx/src/nvVideoEffectsProxy.cpp","$sdk/nvvfx/src/nvCVImageProxy.cpp",'-ld3d11','-ldxgi')
} finally { Pop-Location }
