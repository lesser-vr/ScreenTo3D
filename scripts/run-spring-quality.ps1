param(
    [string]$OutputDirectory,
    [string]$SourceDirectory,
    [ValidateSet('da2-small','da2-base','vda-small','ovda-small-c16')][string[]]$Model,
    [switch]$NonCommercial,
    [switch]$Prepare
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $root ('out/spring-quality-'+(Get-Date -Format 'yyyyMMdd-HHmmss')) }
if (-not $SourceDirectory) { $SourceDirectory=Join-Path $root 'out/spring-source' }
$priorPythonPath=$env:PYTHONPATH
$env:PYTHONPATH=(@('out/spring-python-deps','experiments/ovda','v1','out/gui-python-deps','out/capture-python-deps','out/ovda-python-deps','out/v1-python-deps') | ForEach-Object { Join-Path $root $_ }) -join ';'
$python=Join-Path $root 'out/vda-oracle-env/Scripts/python.exe'
Push-Location $root
try {
    if ($Prepare) {
        & $python (Join-Path $root 'v1/prepare_spring_subset.py') --root $SourceDirectory --download
        if ($LASTEXITCODE) { throw 'Spring subset preparation failed.' }
    }
    $qualityArguments=@((Join-Path $root 'v1/evaluate_spring_quality.py'),'--source',$SourceDirectory,'--output',$OutputDirectory)
    foreach ($name in $Model) { $qualityArguments+=@('--model',$name) }
    if ($NonCommercial) { $qualityArguments+='--noncommercial' }
    & $python @qualityArguments
    if ($LASTEXITCODE) { throw 'Spring quality measurement failed; inspect the partial report and error output.' }
} finally { Pop-Location; $env:PYTHONPATH=$priorPythonPath }
