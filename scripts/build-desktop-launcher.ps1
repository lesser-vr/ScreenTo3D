param([string]$Python = '',[string]$PythonZip = '',[switch]$InstallSource)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (-not $Python) {
    $Python = Join-Path $repo 'out/vda-oracle-env/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $Python)) { $Python = 'python' }
}
& $Python (Join-Path $PSScriptRoot 'build-translations.py') --native-only
if ($LASTEXITCODE) { throw 'Launcher translation generation failed.' }
if (-not $PythonZip) { $PythonZip = Join-Path $repo 'out/desktop-distribution/python-3.13.9-embed-amd64.zip' }
if (Test-Path -LiteralPath $PythonZip) {
    & $Python (Join-Path $PSScriptRoot 'prepare-source-python.py') $PythonZip
    if ($LASTEXITCODE) { throw 'Source interpreter preparation failed.' }
}
$build = Join-Path $repo 'out/desktop-launcher'
$source = Join-Path $repo 'native/launcher'
New-Item -ItemType Directory -Path $build -Force | Out-Null
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'MSVC 2022 build tools are required.' }
& (Join-Path $vs 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
# Convert the approved artwork to Windows Explorer/taskbar resource sizes.
Add-Type -AssemblyName System.Drawing
$icon = [System.IO.BinaryWriter]::new([System.IO.File]::Create((Join-Path $build 'screento3d.ico')))
try {
    $sizes = @(16, 20, 24, 32, 40, 48, 64, 128, 256)
    $images = @()
    $artwork = [System.Drawing.Image]::FromFile((Join-Path $repo 'v1/screento3d_app/assets/screento3d.png'))
    foreach ($size in $sizes) {
        $bitmap = [System.Drawing.Bitmap]::new($size, $size)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $graphics.DrawImage($artwork, 0, 0, $size, $size)
        $memory = [System.IO.MemoryStream]::new()
        $bitmap.Save($memory, [System.Drawing.Imaging.ImageFormat]::Png)
        $images += ,$memory.ToArray()
        $memory.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
    }
    $artwork.Dispose()
    $icon.Write([uint16]0); $icon.Write([uint16]1); $icon.Write([uint16]$sizes.Count)
    $offset = 6 + 16 * $sizes.Count
    for ($i = 0; $i -lt $sizes.Count; $i++) {
        $dimension = $sizes[$i] % 256
        $icon.Write([byte]$dimension); $icon.Write([byte]$dimension)
        $icon.Write([uint16]0); $icon.Write([uint16]1); $icon.Write([uint16]32)
        $icon.Write([uint32]$images[$i].Length); $icon.Write([uint32]$offset)
        $offset += $images[$i].Length
    }
    foreach ($bytes in $images) { $icon.Write([byte[]]$bytes) }
} finally { $icon.Dispose() }
Copy-Item -LiteralPath (Join-Path $build 'screento3d.ico') -Destination (Join-Path $repo 'v1/screento3d_app/assets/screento3d.ico') -ErrorAction Stop
Push-Location $build
try {
    & rc.exe /nologo /I $build /I $source /fo app.res (Join-Path $source 'app.rc')
    if ($LASTEXITCODE) { throw 'Launcher resources failed.' }
    & cl.exe /nologo /std:c++17 /EHsc /MT /O2 /utf-8 (Join-Path $source 'main.cpp') app.res /Fe:ScreenTo3D.exe /link /SUBSYSTEM:WINDOWS /MANIFEST:NO user32.lib shell32.lib ole32.lib advapi32.lib
    if ($LASTEXITCODE) { throw 'Launcher build failed.' }
    $hostBuild = Join-Path $build 'host'
    New-Item -ItemType Directory -Path $hostBuild -Force | Out-Null
    # /MD shares CPython's UCRT so inherited stdout/stderr also work in workers.
    & cl.exe /nologo /std:c++17 /EHsc /MD /O2 /utf-8 (Join-Path $source 'python_host.cpp') app.res ("/Fe:" + (Join-Path $hostBuild 'ScreenTo3D.exe')) /link /SUBSYSTEM:WINDOWS /MANIFEST:NO user32.lib shell32.lib
    if ($LASTEXITCODE) { throw 'Branded Python host build failed.' }
} finally { Pop-Location }
if ($InstallSource) {
    $sourceRuntime = Join-Path $repo 'out/desktop-python'
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRuntime 'python313.dll'))) { throw 'Prepare the pinned source runtime before installing the launcher.' }
    # Install the host first, so the new launcher never points at a missing host.
    Copy-Item -LiteralPath (Join-Path $build 'host/ScreenTo3D.exe') -Destination (Join-Path $sourceRuntime 'ScreenTo3D.exe') -ErrorAction Stop
    Copy-Item -LiteralPath (Join-Path $build 'ScreenTo3D.exe') -Destination (Join-Path $repo 'ScreenTo3D.exe') -ErrorAction Stop
}
