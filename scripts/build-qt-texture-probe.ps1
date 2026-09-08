$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sdk = Join-Path $repoRoot 'out/qt-sdk/6.10.2/msvc2022_64'
if (-not (Test-Path "$sdk/include/QtQuick/QQuickItem")) { throw 'Matching Qt 6.10.2 SDK missing' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$buildDir = Join-Path $repoRoot 'out/qt-texture-probe'
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Push-Location $buildDir
try {
    & nvcc -O2 -arch=sm_120 -std=c++17 -shared -Xcompiler /MD -Xcompiler /utf-8 (Join-Path $repoRoot 'experiments/cuda_projection/qt_texture_source.cu') -o qt_texture_source.dll -ld3d11 -ldxgi
    if ($LASTEXITCODE -ne 0) { throw 'CUDA source build failed' }
    & cl.exe /nologo /std:c++17 /Zc:__cplusplus /permissive- /EHsc /MD /O2 /utf-8 /DQT_NO_DEBUG /I"$sdk/include" /I"$sdk/include/QtCore" /I"$sdk/include/QtGui" /I"$sdk/include/QtQuick" (Join-Path $repoRoot 'experiments/cuda_projection/qt_texture_probe.cpp') /Fe:qt_texture_probe.exe /link /LIBPATH:"$sdk/lib" Qt6Core.lib Qt6Gui.lib Qt6Quick.lib qt_texture_source.lib
    if ($LASTEXITCODE -ne 0) { throw 'Qt probe build failed' }
    & nvcc -O2 -arch=sm_120 -std=c++17 -Xcompiler /MD -Xcompiler /utf-8 (Join-Path $repoRoot 'experiments/cuda_projection/qt_texture_worker.cu') -o qt_texture_worker.exe -ld3d11 -ldxgi
    if ($LASTEXITCODE -ne 0) { throw 'CUDA worker build failed' }
    & cl.exe /nologo /std:c++17 /Zc:__cplusplus /permissive- /EHsc /MD /O2 /utf-8 /LD /DQT_NO_DEBUG /I"$sdk/include" /I"$sdk/include/QtCore" (Join-Path $repoRoot 'experiments/cuda_projection/qt_texture_ipc_source.cpp') /Fe:qt_texture_ipc_source.dll /link /LIBPATH:"$sdk/lib" Qt6Core.lib d3d11.lib dxgi.lib
    if ($LASTEXITCODE -ne 0) { throw 'IPC consumer build failed' }
    & cl.exe /nologo /std:c++17 /Zc:__cplusplus /permissive- /EHsc /MD /O2 /utf-8 /DQT_NO_DEBUG /I"$sdk/include" /I"$sdk/include/QtCore" /I"$sdk/include/QtGui" /I"$sdk/include/QtQuick" (Join-Path $repoRoot 'experiments/cuda_projection/qt_texture_probe.cpp') /Fe:qt_texture_ipc_probe.exe /link /LIBPATH:"$sdk/lib" Qt6Core.lib Qt6Gui.lib Qt6Quick.lib qt_texture_ipc_source.lib
    if ($LASTEXITCODE -ne 0) { throw 'IPC Qt probe build failed' }
} finally { Pop-Location }
[ordered]@{
    qt_version = '6.10.2'
    sdk = $sdk
    nvcc_version = (& nvcc --version | Out-String).Trim()
    executable_sha256 = (Get-FileHash "$buildDir/qt_texture_probe.exe").Hash
    source_dll_sha256 = (Get-FileHash "$buildDir/qt_texture_source.dll").Hash
    ipc_executable_sha256 = (Get-FileHash "$buildDir/qt_texture_ipc_probe.exe").Hash
    ipc_source_dll_sha256 = (Get-FileHash "$buildDir/qt_texture_ipc_source.dll").Hash
    worker_sha256 = (Get-FileHash "$buildDir/qt_texture_worker.exe").Hash
    native_sources = @(Get-FileHash (Join-Path $repoRoot 'experiments/cuda_projection/qt_texture_probe.cpp'), (Join-Path $repoRoot 'experiments/cuda_projection/qt_texture_source.cu'), (Join-Path $repoRoot 'experiments/cuda_projection/qt_texture_ipc_source.cpp'), (Join-Path $repoRoot 'experiments/cuda_projection/qt_texture_worker.cu'), (Join-Path $repoRoot 'experiments/cuda_projection/texture_handoff_probe.cu') | Select-Object Path,Hash)
    scope = 'Standalone synthetic Qt interop; no application mutation'
} | ConvertTo-Json | Set-Content -LiteralPath "$buildDir/build-manifest.json" -Encoding UTF8
