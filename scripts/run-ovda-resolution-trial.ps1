param(
    [ValidateSet('fp32-current','encoder-spatial','low-fp32','low-fp16')]
    [string]$Variant = 'encoder-spatial'
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$priorPythonPath=$env:PYTHONPATH
$env:PYTHONPATH=(@('experiments/ovda','v1','out/gui-python-deps','out/capture-python-deps','out/ovda-python-deps','out/v1-python-deps') | ForEach-Object { Join-Path $root $_ }) -join ';'
Push-Location $root
try {
    & (Join-Path $root 'out/vda-oracle-env/Scripts/python.exe') (Join-Path $root 'experiments/ovda/resolution_trial_gui.py') --variant $Variant
    if ($LASTEXITCODE) { throw 'oVDA 시험 실행이 실패했습니다.' }
} finally { Pop-Location; $env:PYTHONPATH=$priorPythonPath }
