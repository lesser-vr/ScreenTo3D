$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw 'C++ build tools missing' }
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$buildDir = Join-Path $repoRoot 'out/live-texture-handoff'
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Push-Location $buildDir
try {
    & nvcc -O2 -arch=sm_120 -std=c++17 -Xcompiler /MD -Xcompiler /utf-8 (Join-Path $repoRoot 'experiments/cuda_projection/texture_handoff_probe.cu') -o texture_handoff_probe.exe -ld3d11 -ldxgi
    if ($LASTEXITCODE -ne 0) { throw 'Texture handoff probe build failed' }
} finally { Pop-Location }
[ordered]@{
    nvcc_version = (& nvcc --version | Out-String).Trim()
    host_compiler = (Get-Command cl.exe).Source
    architecture = 'sm_120'
    source_sha256 = (Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/texture_handoff_probe.cu')).Hash
    exe_sha256 = (Get-FileHash (Join-Path $buildDir 'texture_handoff_probe.exe')).Hash
    scope = 'Standalone synthetic boundary probe; not integrated GUI or capture'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildDir 'build-manifest.json') -Encoding UTF8
