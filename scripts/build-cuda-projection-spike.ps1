param([switch]$GpuPreview, [string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw 'C++ build tools missing.' }
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$output = Join-Path $repoRoot 'out/cuda-projection-spike'
if ($GpuPreview) { $output = Join-Path $repoRoot 'out/cuda-projection-preview' }
if ($OutputDirectory) {
    $output = [System.IO.Path]::GetFullPath($OutputDirectory)
    if (Test-Path -LiteralPath (Join-Path $output 'projection.dll')) { throw 'Choose a new fixture directory; existing DLL is preserved.' }
}
New-Item -ItemType Directory -Path $output -Force | Out-Null
Push-Location $output
try {
    $defines = @()
    if ($GpuPreview) { $defines = @('-DSCREENTO3D_GPU_PREVIEW=1') }
    # Local RTX 5090 spike only; deliberately not a multi-architecture release.
    & nvcc @defines -shared -O2 --fmad=false -arch=sm_120 -std=c++17 -Xcompiler /MD -Xcompiler /utf-8 `
        (Join-Path $repoRoot 'experiments/cuda_projection/projection.cu') -o projection.dll
    if ($LASTEXITCODE -ne 0) { throw 'CUDA projection experiment build failed.' }
    if ($GpuPreview) {
        $exports = (& dumpbin /exports projection.dll | Out-String)
        if ($LASTEXITCODE -ne 0 -or $exports -match 'projection_create_injected') { throw 'Preview export audit failed.' }
    }
} finally { Pop-Location }
[ordered]@{
    nvcc = (Get-Command nvcc).Source
    nvcc_version = (& nvcc --version | Out-String).Trim()
    host_compiler = (Get-Command cl.exe).Source
    architecture = 'sm_120'
    scope = 'Local experiment or opt-in preview only; not a public release binary'
    gpu_preview = [bool]$GpuPreview
    source_sha256 = (Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/projection.cu')).Hash
    dll_sha256 = (Get-FileHash (Join-Path $output 'projection.dll')).Hash
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'build-manifest.json') -Encoding UTF8
Write-Output (Join-Path $output 'projection.dll')
