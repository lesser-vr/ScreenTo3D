param()
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo 'out/vda-oracle-env/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Prepare the local model environment first.' }
if (-not (Test-Path -LiteralPath (Join-Path $repo 'out/gui-python-deps/PySide6'))) {
    throw 'GUI dependencies missing. Install v1/requirements-gui.txt into out/gui-python-deps using the prepared Python.'
}
$priorPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = (@('v1', 'out/gui-python-deps', 'out/capture-python-deps', 'out/v1-python-deps') | ForEach-Object { Join-Path $repo $_ }) -join ';'
    Start-Process -FilePath $python -ArgumentList @('-m', 'depthsbs_app.desktop') -WorkingDirectory $repo -WindowStyle Hidden
} finally { $env:PYTHONPATH = $priorPythonPath }
