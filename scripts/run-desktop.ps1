param([switch]$RowFlow)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo 'out/desktop-python/pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Prepare the local model environment first.' }
if (-not (Test-Path -LiteralPath (Join-Path $repo 'out/gui-python-deps/PySide6'))) {
    throw 'GUI dependencies missing. Install v1/requirements-gui.txt into out/gui-python-deps using the prepared Python.'
}
$priorPythonPath = $env:PYTHONPATH
$priorRenderer = $env:SCREENTO3D_STEREO_RENDERER
try {
    if ($RowFlow) {
        $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
        $vsPath = & $vswhere -latest -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if (-not $vsPath) { throw 'RowFlow compilation requires the prepared MSVC tools.' }
        & (Join-Path $vsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
        $env:SCREENTO3D_STEREO_RENDERER = 'rowflow-sym'
    }
    $env:PYTHONPATH = (@('v1', 'out/gui-python-deps', 'out/capture-python-deps', 'out/v1-python-deps') | ForEach-Object { Join-Path $repo $_ }) -join ';'
    if ($RowFlow) { $env:PYTHONPATH += ';' + (Join-Path $repo 'out/iw3-compile-deps-20261105') }
    Start-Process -FilePath $python -ArgumentList @('-m', 'screento3d_app.desktop') -WorkingDirectory $repo -WindowStyle Hidden
} finally { $env:PYTHONPATH = $priorPythonPath; $env:SCREENTO3D_STEREO_RENDERER = $priorRenderer }
