param(
    [string]$OutputDirectory,
    [string]$SourceDirectory,
    [ValidateSet('da2-small','da2-base','vda-small','ovda-small-c16')][string[]]$Model,
    [switch]$NonCommercial,
    [switch]$Prepare
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $root ('out/sbs-rgb-quality-'+(Get-Date -Format 'yyyyMMdd-HHmmss')) }
if (-not $SourceDirectory) { $SourceDirectory=Join-Path $root 'out/sbs-rgb-fixture-20261110' }
$priorPythonPath=$env:PYTHONPATH
$env:PYTHONPATH=(@('out/sbs-quality-python-deps','out/spring-python-deps','experiments/ovda','v1','out/gui-python-deps','out/capture-python-deps','out/ovda-python-deps','out/v1-python-deps') | ForEach-Object { Join-Path $root $_ }) -join ';'
$python=Join-Path $root 'out/vda-oracle-env/Scripts/python.exe'
Push-Location $root
try {
    if ($Prepare -and -not (Test-Path -LiteralPath (Join-Path $SourceDirectory 'manifest.json'))) {
        & $python (Join-Path $root 'v1/sbs_rgb_fixture.py') --output $SourceDirectory
        if ($LASTEXITCODE) { throw 'SBS reference fixture preparation failed.' }
    }
    if ($Prepare) {
        & $python (Join-Path $root 'v1/prepare_sbs_rgb_metrics.py')
        if ($LASTEXITCODE) { throw 'Official metric weight preparation failed.' }
    }
    $qualityArguments=@((Join-Path $root 'v1/evaluate_sbs_rgb.py'),'--source',$SourceDirectory,'--output',$OutputDirectory)
    foreach ($name in $Model) { $qualityArguments+=@('--model',$name) }
    if ($NonCommercial) { $qualityArguments+='--noncommercial' }
    & $python @qualityArguments
    if ($LASTEXITCODE) { throw 'Native SBS RGB comparison failed; inspect the partial report and error output.' }
} finally { Pop-Location; $env:PYTHONPATH=$priorPythonPath }
