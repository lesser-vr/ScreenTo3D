# Personal non-commercial oVDA preview. See LICENSE and README.md in this folder.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InputVideo,
    [Parameter(Mandatory=$true)][string]$OutputVideo
)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pythonPath=Join-Path $repoRoot 'out/vda-oracle-env/Scripts/python.exe'
$oldPythonPath=$env:PYTHONPATH
try {
    $env:PYTHONPATH=@($PSScriptRoot,(Join-Path $repoRoot 'v1'),(Join-Path $repoRoot 'out/ovda-python-deps'),(Join-Path $repoRoot 'out/v1-python-deps')) -join ';'
    & $pythonPath (Join-Path $PSScriptRoot 'run.py') --input $InputVideo --output $OutputVideo
    if($LASTEXITCODE -ne 0){throw 'oVDA preview failed. No alternate backend was selected.'}
} finally {
    $env:PYTHONPATH=$oldPythonPath
}
