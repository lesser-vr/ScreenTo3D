param([ValidateSet('live-texture-projection','live-texture-publish','live-texture-pool','live-texture-runtime','live-texture-runtime-consume','ovda-device-texture-spike','vda-device-texture-spike')][string]$OutputName = 'live-texture-projection')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$buildDir = Join-Path $repoRoot "out/$OutputName"
$sourceName = $OutputName.Replace('-','_')
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Push-Location $buildDir
try {
    & nvcc -shared -O2 --fmad=false -arch=sm_120 -std=c++17 -Xcompiler /MD -Xcompiler /utf-8 (Join-Path $repoRoot "experiments/cuda_projection/$sourceName.cu") -o "$sourceName.dll" -ld3d11 -ldxgi
    if ($LASTEXITCODE -ne 0) { throw 'Texture projection build failed' }
} finally { Pop-Location }
[ordered]@{
    nvcc_version = (& nvcc --version | Out-String).Trim()
    scope = 'Separate diagnostic DLL; borrowed pinned LiveDepth layout, not application path'
    live_layout_sha256 = (Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/live_depth.cu')).Hash
    source_sha256 = (Get-FileHash (Join-Path $repoRoot "experiments/cuda_projection/$sourceName.cu")).Hash
    dll_sha256 = (Get-FileHash (Join-Path $buildDir "$sourceName.dll")).Hash
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildDir 'build-manifest.json') -Encoding UTF8
