param([switch]$Diagnostics,
    [ValidateSet('gpu-load-opt','guide-fp32','guide-compensated','guide-common','guide-fixed8','guide-two-thirds','static-sbs')][string]$OutputName='static-sbs',
    [switch]$DepthOnly,[switch]$CompanionsOnly)
$ErrorActionPreference = 'Stop'
if ($DepthOnly -and $CompanionsOnly) { throw 'Select at most one partial build scope' }
$repoRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$buildDir = Join-Path $repoRoot "out/$OutputName"
$guideFlags = @()
if ($OutputName -eq 'guide-fp32') { $guideFlags += '-DDEPTHSBS_GUIDE_FLOAT=1' }
if ($OutputName -in @('guide-compensated','guide-common','guide-fixed8','guide-two-thirds','static-sbs')) { $guideFlags += '-DDEPTHSBS_GUIDE_COMPENSATED=1' }
if ($OutputName -eq 'guide-two-thirds') { $guideFlags += '-DDEPTHSBS_GUIDE_TWO_THIRDS=1' }
if ($OutputName -in @('guide-fixed8','static-sbs')) { $guideFlags += '-DDEPTHSBS_FIXED_GUIDE_8=1' }
New-Item -ItemType Directory -Force $buildDir | Out-Null
Push-Location $buildDir
try {
    $sources = @('live_depth','live_texture_runtime','small_input')
    if ($DepthOnly) { $sources = @('live_depth') }
    if ($CompanionsOnly) { $sources = @('live_texture_runtime','small_input') }
    if ($Diagnostics) { $sources += @('resolve_probe','guide_sum_probe') }
    foreach ($sourceName in $sources) {
        & nvcc -shared -O2 --fmad=false -arch=sm_120 -std=c++17 -DDEPTHSBS_FAST_GUIDE=1 -DDEPTHSBS_BITMAP_RESOLVE=1 @guideFlags -Xcompiler /MD -Xcompiler /utf-8 (Join-Path $repoRoot "experiments/cuda_projection/$sourceName.cu") -o "$sourceName.dll" -ld3d11 -ldxgi
        if ($LASTEXITCODE -ne 0) { throw "GPU load candidate build failed: $sourceName" }
    }
    [ordered]@{
        architecture='sm_120';flags='-O2 --fmad=false; DEPTHSBS_FAST_GUIDE, DEPTHSBS_BITMAP_RESOLVE'
        guide_accumulation=$OutputName;guide_flags=$guideFlags
        fixed_guide_radii=if ($OutputName -in @('guide-fixed8','static-sbs')) { @(4,8,12) } else { @(4,12) }
        scope='Prepared-local pinned runtime; not a public release'
        nvcc_version=(& nvcc --version | Out-String).Trim()
        host_compiler=(Get-Command cl.exe).Source
        sources=@('live_depth.cu','guide_fixed.cuh','guide_reduced.cuh','resolve_parallel.cuh','projection.cu','live_texture_runtime.cu','live_texture_publish.cu','live_texture_projection.cu','stereo_detail.cuh','small_input.cu','base_input.cu') | ForEach-Object {
            @{name=$_;sha256=(Get-FileHash (Join-Path $repoRoot "experiments/cuda_projection/$_")).Hash}
        }
        dlls=Get-ChildItem $buildDir -Filter '*.dll' | ForEach-Object { @{name=$_.Name;sha256=(Get-FileHash $_.FullName).Hash} }
    } | ConvertTo-Json -Depth 5 | Set-Content build-manifest.json
    $sourceText=Get-Content (Join-Path $repoRoot 'experiments/cuda_projection/base_input.cu') -Raw
    $sourceText.Substring(0,$sourceText.IndexOf('//M*/')+5) | Set-Content OPENCV-NOTICE.txt
} finally { Pop-Location }
