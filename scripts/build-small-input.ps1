$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw 'C++ build tools missing' }
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$buildDir = Join-Path $repoRoot 'out/small-input-detail'
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Push-Location $buildDir
try {
    & nvcc -shared -O2 --fmad=false -arch=sm_120 -std=c++17 -Xcompiler /MD -Xcompiler /utf-8 (Join-Path $repoRoot 'experiments/cuda_projection/small_input.cu') -o small_input.dll
    if ($LASTEXITCODE -ne 0) { throw 'Small CUDA input build failed' }
} finally { Pop-Location }
[ordered]@{
    architecture = 'sm_120'
    nvcc_version = (& nvcc --version | Out-String).Trim()
    sources = @( 'small_input.cu','stereo_detail.cuh','live_depth.cu','base_input.cu','projection.cu','resolve_parallel.cuh' ) | ForEach-Object {
        [ordered]@{ name = $_; sha256 = (Get-FileHash (Join-Path $repoRoot "experiments/cuda_projection/$_")).Hash }
    }
    dll_sha256 = (Get-FileHash (Join-Path $buildDir 'small_input.dll')).Hash
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $buildDir 'build-manifest.json') -Encoding UTF8
$sourceText = Get-Content -LiteralPath (Join-Path $repoRoot 'experiments/cuda_projection/base_input.cu') -Raw
$sourceText.Substring(0, $sourceText.IndexOf('//M*/') + 5) | Set-Content -LiteralPath (Join-Path $buildDir 'OPENCV-NOTICE.txt') -Encoding UTF8
Get-FileHash (Join-Path $buildDir 'small_input.dll')
