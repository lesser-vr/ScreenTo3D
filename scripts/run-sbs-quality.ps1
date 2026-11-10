param(
    [string]$OutputDirectory,
    [ValidateRange(32,360)][int]$Frames=120,
    [ValidateSet('da2-small','da2-base','vda-small','ovda-small-c16')][string[]]$Model,
    [switch]$NonCommercial
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $root ('out/sbs-quality-'+(Get-Date -Format 'yyyyMMdd-HHmmss')) }
$priorPythonPath=$env:PYTHONPATH
$env:PYTHONPATH=(@('experiments/ovda','v1','out/gui-python-deps','out/capture-python-deps','out/ovda-python-deps','out/v1-python-deps') | ForEach-Object { Join-Path $root $_ }) -join ';'
$qualityArguments=@((Join-Path $root 'v1/evaluate_sbs_quality.py'),'--output',$OutputDirectory,'--frames',$Frames)
foreach ($name in $Model) { $qualityArguments+=@('--model',$name) }
if ($NonCommercial) { $qualityArguments+='--noncommercial' }
Push-Location $root
try {
    & (Join-Path $root 'out/vda-oracle-env/Scripts/python.exe') @qualityArguments
    if ($LASTEXITCODE) { throw 'SBS quality measurement failed; inspect report.json and the error output.' }
} finally { Pop-Location; $env:PYTHONPATH=$priorPythonPath }
