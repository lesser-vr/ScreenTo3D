$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath=& $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $vsPath){throw 'C++ build tools missing'}
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$build=Join-Path $root 'out/live-motion-static'
$headers=Join-Path $root 'out/nvof-sdk-headers'
New-Item -ItemType Directory -Path $build -Force | Out-Null
Push-Location $build
try {
    & nvcc -shared -O2 --fmad=false -arch=sm_120 -std=c++17 -Xcompiler /EHsc -Xcompiler /MD -Xcompiler /utf-8 -I $headers (Join-Path $root 'experiments/optical_flow/live_motion.cu') -o live_motion.dll -lcuda -Xlinker /NODEFAULTLIB:LIBCMT
    if($LASTEXITCODE -ne 0){throw 'Live motion CUDA build failed'}
    [ordered]@{scope='Local owned one-frame GPU motion history'; architecture='sm_120';
        source_sha256=(Get-FileHash (Join-Path $root 'experiments/optical_flow/live_motion.cu')).Hash;
        layout_sha256=(Get-FileHash (Join-Path $root 'experiments/cuda_projection/live_depth.cu')).Hash;
        common_header_sha256=(Get-FileHash (Join-Path $headers 'nvOpticalFlowCommon.h')).Hash;
        cuda_header_sha256=(Get-FileHash (Join-Path $headers 'nvOpticalFlowCuda.h')).Hash;
    detail_source_sha256 = (Get-FileHash (Join-Path $root 'experiments/cuda_projection/stereo_detail.cuh')).Hash;
        dll_sha256=(Get-FileHash live_motion.dll).Hash} | ConvertTo-Json | Set-Content build-manifest.json
} finally {Pop-Location}
Get-FileHash (Join-Path $build 'live_motion.dll')
