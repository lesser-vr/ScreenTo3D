$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sdk = Join-Path $repoRoot 'out/qt-sdk/6.10.2/msvc2022_64'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$buildDir = Join-Path $repoRoot 'out/qt-native-delivery'
$source = Join-Path $repoRoot 'experiments/cuda_projection/qt_native_delivery.cpp'
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Push-Location $buildDir
try {
    & "$sdk/bin/moc.exe" -I"$sdk/include" -I"$sdk/include/QtCore" -I"$sdk/include/QtGui" -I"$sdk/include/QtQuick" $source -o qt_native_delivery.moc
    if ($LASTEXITCODE -ne 0) { throw 'Native QML metadata build failed' }
    & cl.exe /nologo /std:c++17 /Zc:__cplusplus /permissive- /EHsc /MD /O2 /utf-8 /LD /DQT_NO_DEBUG /I"$buildDir" /I"$sdk/include" /I"$sdk/include/QtCore" /I"$sdk/include/QtGui" /I"$sdk/include/QtQuick" /I"$sdk/include/QtQml" $source /Fe:qt_native_delivery.dll /link /LIBPATH:"$sdk/lib" Qt6Core.lib Qt6Gui.lib Qt6Quick.lib Qt6Qml.lib d3d11.lib dxgi.lib
    if ($LASTEXITCODE -ne 0) { throw 'Native Qt delivery build failed' }
} finally { Pop-Location }
[ordered]@{
    qt_version = '6.10.2'
    source_sha256 = (Get-FileHash $source).Hash
    dll_sha256 = (Get-FileHash "$buildDir/qt_native_delivery.dll").Hash
    scope = 'Experimental pure D3D11/Qt two-consumer delivery; no CUDA dependency'
} | ConvertTo-Json | Set-Content -LiteralPath "$buildDir/build-manifest.json" -Encoding UTF8
