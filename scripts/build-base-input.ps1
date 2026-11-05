$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw 'C++ build tools missing' }
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$buildDir = Join-Path $repoRoot 'out/base-input'
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Push-Location $buildDir
try {
    & nvcc -shared -O2 --fmad=false -arch=sm_120 -std=c++17 -Xcompiler /MD -Xcompiler /utf-8 (Join-Path $repoRoot 'experiments/cuda_projection/base_input.cu') -o base_input.dll
    if ($LASTEXITCODE -ne 0) { throw 'Base input CUDA build failed' }
} finally { Pop-Location }
[ordered]@{
    nvcc_version = (& nvcc --version | Out-String).Trim()
    architecture = 'sm_120'
    source_sha256 = (Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/base_input.cu')).Hash
    dll_sha256 = (Get-FileHash (Join-Path $buildDir 'base_input.dll')).Hash
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildDir 'build-manifest.json') -Encoding UTF8
Get-FileHash (Join-Path $buildDir 'base_input.dll')
$sourceText = Get-Content -LiteralPath (Join-Path $repoRoot 'experiments/cuda_projection/base_input.cu') -Raw
$sourceText.Substring(0, $sourceText.IndexOf('//M*/') + 5) | Set-Content -LiteralPath (Join-Path $buildDir 'OPENCV-NOTICE.txt') -Encoding UTF8
