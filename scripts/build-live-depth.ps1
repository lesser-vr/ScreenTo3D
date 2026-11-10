param([ValidateSet('live-depth-candidate', 'live-depth-parallel', 'live-depth-stereo-lr', 'live-depth-stable', 'live-depth-coverage', 'live-depth-range', 'live-depth-window', 'live-depth-budget', 'live-depth-detail', 'live-depth-guide-shared', 'live-depth-guide-profile', 'live-depth-guide-rolling', 'live-depth-guide-hybrid', 'live-depth-guide-promoted', 'ovda-device-post-spike')][string]$OutputName = 'live-depth-detail')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw 'C++ build tools missing' }
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$buildDir = Join-Path $repoRoot "out/$OutputName"
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Push-Location $buildDir
try {
    $sourceName = switch ($OutputName) {
        'live-depth-guide-shared' { 'live_depth_guide_shared.cu' }
        'live-depth-guide-profile' { 'live_depth_guide_profile.cu' }
        'live-depth-guide-rolling' { 'live_depth_guide_rolling.cu' }
        'live-depth-guide-hybrid' { 'live_depth_guide_hybrid.cu' }
        default { 'live_depth.cu' }
    }
    & nvcc -shared -O2 --fmad=false -arch=sm_120 -std=c++17 -Xcompiler /MD -Xcompiler /utf-8 (Join-Path $repoRoot "experiments/cuda_projection/$sourceName") -o live_depth.dll
    if ($LASTEXITCODE -ne 0) { throw 'Live depth CUDA build failed' }
} finally { Pop-Location }
[ordered]@{
    nvcc_version = (& nvcc --version | Out-String).Trim()
    host_compiler = (Get-Command cl.exe).Source
    architecture = 'sm_120'
    scope = if ($OutputName -in @('live-depth-range','live-depth-window','live-depth-budget')) { 'Prepared-local product DLL; not a public release' } else { 'Opt-in local candidate; not a public release' }
    guide_implementation = switch ($OutputName) {
        'live-depth-guide-shared' { 'shared-memory exact-order candidate' }
        'live-depth-guide-profile' { 'global-memory reference with diagnostic subkernel events' }
        'live-depth-guide-rolling' { 'non-exact chunked rolling-window candidate' }
        'live-depth-guide-hybrid' { 'exact radius-4 plus rolling radius-8/12 candidate' }
        'live-depth-guide-promoted' { 'production source with exact radius-4 and rolling radius-8/12 guide' }
        'live-depth-parallel' { 'production exact radius-4 plus rolling radius-8/12 guide' }
        'live-depth-stereo-lr' { 'production guide with physical left/right forward disparity' }
        'live-depth-stable' { 'production guide with optional bounded subpixel reconstruction and sparse depth sampling' }
        'live-depth-coverage' { 'production guide with bounded fractional silhouette coverage' }
        'live-depth-range' { 'coverage plus optional source-time adaptive range response' }
        'live-depth-window' { 'range/coverage plus optional bounded floating stereo window' }
        'live-depth-budget' { 'window plus optional fixed compression-only disparity curve' }
        'live-depth-detail' { 'budget plus selective contour and bounded background fill' }
        default { 'global-memory reference' }
    }
    source_sha256 = (Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/live_depth.cu')).Hash
    candidate_source_sha256 = if ($sourceName -ne 'live_depth.cu') { (Get-FileHash (Join-Path $repoRoot "experiments/cuda_projection/$sourceName")).Hash } else { $null }
    projection_source_sha256 = (Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/projection.cu')).Hash
    resolve_source_sha256 = (Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/resolve_parallel.cuh')).Hash
    detail_source_sha256 = (Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/stereo_detail.cuh')).Hash
    dll_sha256 = (Get-FileHash (Join-Path $buildDir 'live_depth.dll')).Hash
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildDir 'build-manifest.json') -Encoding UTF8
Get-FileHash (Join-Path $buildDir 'live_depth.dll')
