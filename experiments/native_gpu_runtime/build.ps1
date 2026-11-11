$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vs 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$output = Join-Path $root 'out/native-gpu-runtime'
New-Item -ItemType Directory -Path $output -Force | Out-Null
Push-Location $output
try {
    & nvcc -shared -O2 --fmad=false -std=c++17 '-gencode=arch=compute_75,code=compute_75' '-gencode=arch=compute_120,code=sm_120' -Xcompiler /MD -Xcompiler /utf-8 (Join-Path $PSScriptRoot 'convert.cu') -o native_rgb.dll
    if ($LASTEXITCODE) { throw 'Native RGB probe build failed.' }
} finally { Pop-Location }
