param([ValidateSet('half-render-trial','half-render-scratch')][string]$OutputName='half-render-scratch')
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vs 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$build = Join-Path $repo "out/$OutputName"
New-Item -ItemType Directory -Path $build -Force | Out-Null
Push-Location $build
try {
    & nvcc -shared -O2 --fmad=false '-gencode=arch=compute_75,code=compute_75' '-gencode=arch=compute_120,code=sm_120' -std=c++17 -Xcompiler /MD -Xcompiler /utf-8 -DDEPTHSBS_FAST_GUIDE=1 -DDEPTHSBS_BITMAP_RESOLVE=1 -DDEPTHSBS_GUIDE_COMPENSATED=1 -DDEPTHSBS_FIXED_GUIDE_8=1 (Join-Path $repo 'experiments/cuda_projection/half_render_trial.cu') -o half_render_trial.dll -ld3d11 -ldxgi
    if ($LASTEXITCODE) { throw 'Half render trial build failed.' }
    Get-FileHash half_render_trial.dll | Select-Object Hash
} finally { Pop-Location }
