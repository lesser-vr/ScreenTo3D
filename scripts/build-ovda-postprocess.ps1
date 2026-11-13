# Source-only optional oVDA bridge; retains the existing borrowed LiveDepth ABI.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vs 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$dir = Join-Path $root 'out/ovda-postprocess-range'
$source = Join-Path $root 'experiments/ovda/postprocess.cu'
New-Item -Type Directory -Force $dir | Out-Null
$priorTmp, $priorTemp = $env:TMP, $env:TEMP
$env:TMP = $env:TEMP = Join-Path $dir 'temp'
New-Item -Type Directory -Force $env:TMP | Out-Null
Push-Location $dir
try {
    & nvcc -shared -O2 --fmad=false '-gencode=arch=compute_75,code=compute_75' '-gencode=arch=compute_120,code=sm_120' -std=c++17 -DSCREENTO3D_FAST_GUIDE=1 -DSCREENTO3D_BITMAP_RESOLVE=1 -DSCREENTO3D_GUIDE_COMPENSATED=1 -DSCREENTO3D_FIXED_GUIDE_8=1 -Xcompiler /MD -Xcompiler /utf-8 $source -o ovda_postprocess.dll
    if ($LASTEXITCODE) { throw 'oVDA postprocessing bridge build failed' }
} finally { Pop-Location; $env:TMP = $priorTmp; $env:TEMP = $priorTemp }
[ordered]@{
    source_sha256 = (Get-FileHash $source).Hash.ToLower()
    live_depth_sha256 = (Get-FileHash (Join-Path $root 'experiments/cuda_projection/live_depth.cu')).Hash.ToLower()
    dll_sha256 = (Get-FileHash (Join-Path $dir 'ovda_postprocess.dll')).Hash.ToLower()
    compiler = (& nvcc --version | Out-String).Trim()
    flags = '--fmad=false; compute_75 PTX; sm_120; same portable guide flags'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dir 'build-manifest.json') -Encoding UTF8
Get-FileHash (Join-Path $dir 'ovda_postprocess.dll')
