param([ValidateSet('nvof-probe', 'nvof-device-warp')][string]$OutputName = 'nvof-probe')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repoRoot 'experiments/optical_flow/nvof_cuda_probe.cu'
$headerRoot = Join-Path $repoRoot 'out/nvof-sdk-headers'
$commonHeader = Join-Path $headerRoot 'nvOpticalFlowCommon.h'
$cudaHeader = Join-Path $headerRoot 'nvOpticalFlowCuda.h'
foreach ($path in @($source, $commonHeader, $cudaHeader)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing pinned NVOF source: $path" }
}
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw 'C++ build tools missing' }
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$buildDir = Join-Path $repoRoot "out/$OutputName"
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
$output = Join-Path $buildDir 'nvof_probe.dll'
& nvcc.exe -std=c++17 -O2 -shared -I $headerRoot -Xcompiler /EHsc -Xcompiler /MD -Xcompiler /utf-8 $source -o $output -lcuda -Xlinker /NODEFAULTLIB:LIBCMT
if ($LASTEXITCODE -ne 0) { throw 'NVOF probe build failed' }
[ordered]@{
    scope = if ($OutputName -eq 'nvof-device-warp') { 'Isolated CUDA NVOF device-depth warp; not an application DLL' } else { 'Isolated official-header CUDA NVOF diagnostic; not an application DLL' }
    output_name = $OutputName
    compiler = (Get-Command nvcc.exe).Source
    source_sha256 = (Get-FileHash $source).Hash
    nvidia_common_header_sha256 = (Get-FileHash $commonHeader).Hash
    nvidia_cuda_header_sha256 = (Get-FileHash $cudaHeader).Hash
    nvidia_header_source = 'https://github.com/NVIDIA/NVIDIAOpticalFlowSDK'
    dll_sha256 = (Get-FileHash $output).Hash
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildDir 'build-manifest.json') -Encoding UTF8
Get-FileHash $output
