param([string]$Output = 'out/d3d11-live-source')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$build = [System.IO.Path]::GetFullPath($Output, $repo)
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Visual Studio C++ Build Tools are required.' }
& (Join-Path $vs 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
New-Item -ItemType Directory -Force -Path $build | Out-Null
Push-Location $build
try {
    & cl.exe /nologo /O2 /MD /EHsc /std:c++17 /utf-8 /W4 /WX (Join-Path $repo 'tests/fixtures/d3d11_live_source.cpp') /Fe:d3d11-live-source.exe /link d3d11.lib dxgi.lib user32.lib
    if ($LASTEXITCODE) { throw 'D3D11 test input build failed.' }
} finally {
    Pop-Location
}
