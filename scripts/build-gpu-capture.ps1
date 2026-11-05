$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$cudaRoot = Split-Path -Parent (Split-Path -Parent (Get-Command nvcc.exe).Source)
$buildDir = Join-Path $repoRoot 'out/gpu-capture'
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Push-Location $buildDir
try {
    & cl /nologo /LD /O2 /MD /EHsc /std:c++17 /utf-8 "/I$cudaRoot/include" (Join-Path $repoRoot 'experiments/cuda_projection/gpu_capture.cpp') /link /OUT:gpu_capture.dll /NODEFAULTLIB:LIBCMT "/LIBPATH:$cudaRoot/lib/x64" cudart_static.lib d3d11.lib dxgi.lib windowsapp.lib user32.lib advapi32.lib
    if ($LASTEXITCODE -ne 0) { throw 'GPU capture build failed' }
} finally { Pop-Location }
[ordered]@{
    source_sha256 = (Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/gpu_capture.cpp')).Hash
    dll_sha256 = (Get-FileHash (Join-Path $buildDir 'gpu_capture.dll')).Hash
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildDir 'build-manifest.json') -Encoding UTF8
Get-FileHash (Join-Path $buildDir 'gpu_capture.dll')
