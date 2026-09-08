param(
    [Parameter(Mandatory = $true)][string]$OutputReport,
    [switch]$NonCommercial,
    [string]$EngineDirectory,
    [string]$RuntimeDirectory = 'C:\TensorRT\TensorRT-11.2.1.2\bin'
)
$ErrorActionPreference = 'Stop'
if (-not $NonCommercial) {
    throw 'Read experiments/ovda/LICENSE and specify -NonCommercial for personal/non-commercial use.'
}
$repo = Split-Path $PSScriptRoot -Parent
$sitePackages = Join-Path $repo 'out/vda-oracle-env/Lib/site-packages'
if (-not (Test-Path -LiteralPath $sitePackages)) { throw 'Prepared oVDA packages are missing.' }
if (-not $EngineDirectory) { $EngineDirectory = Join-Path $repo 'out/ovda-local' }
$python = Join-Path $repo 'out/vda-oracle-env/Scripts/python.exe'
$configuration = Join-Path $repo 'out/vda-oracle-env/pyvenv.cfg'
$configuredHome = if (Test-Path -LiteralPath $configuration) {
    (Get-Content -LiteralPath $configuration | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1) -replace '^home\s*=\s*', ''
}
if (-not $configuredHome -or $configuredHome -like '*\WindowsApps\*' -or
        -not (Test-Path -LiteralPath (Join-Path $configuredHome 'python.exe'))) {
    $python = Get-ChildItem -LiteralPath (Join-Path $env:APPDATA 'uv/python') -Directory -Filter 'cpython-3.13.*-windows-x86_64-none' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object { Join-Path $_.FullName 'python.exe' } |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
}
if (-not $python) { throw 'Unable to resolve a compatible Python 3.13 runtime.' }
$priorPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = (@('v1', 'out/vda-oracle-env/Lib/site-packages', 'out/v1-python-deps') |
        ForEach-Object { Join-Path $repo $_ }) -join ';'
    & $python (Join-Path $repo 'v1/validate_ovda_lifecycle.py') --noncommercial `
        --output $OutputReport --engine-dir $EngineDirectory --runtime-dir $RuntimeDirectory
    if ($LASTEXITCODE -ne 0) { throw "oVDA lifecycle validation exited with code $LASTEXITCODE" }
} finally { $env:PYTHONPATH = $priorPythonPath }
