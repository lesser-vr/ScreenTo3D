param(
    [string]$OutputDirectory,
    [switch]$MediaOnly,
    [ValidateSet('ovda-small-c16','da2-base','da2-small','vda-small')][string]$Model='ovda-small-c16',
    [ValidateSet(2,3)][int]$WindowCount=3
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $root ('out/uniform-background-tc-'+(Get-Date -Format 'yyyyMMdd-HHmmss')) }
$priorPythonPath=$env:PYTHONPATH
$env:PYTHONPATH=(@('experiments/ovda','v1','out/gui-python-deps','out/capture-python-deps','out/ovda-python-deps','out/v1-python-deps') | ForEach-Object { Join-Path $root $_ }) -join ';'
$tcArguments=@((Join-Path $root 'v1/check_uniform_background_tc.py'),'--output',$OutputDirectory,'--model',$Model,'--windows',$WindowCount)
if ($MediaOnly) { $tcArguments+='--media-only' }
Push-Location $root
try {
    & (Join-Path $root 'out/vda-oracle-env/Scripts/python.exe') @tcArguments
    if ($LASTEXITCODE) { throw 'Uniform-background TC failed or inconclusive; see report.json.' }
} finally { Pop-Location; $env:PYTHONPATH=$priorPythonPath }
