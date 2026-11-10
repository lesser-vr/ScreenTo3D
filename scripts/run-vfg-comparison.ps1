param([switch]$Vfg, [switch]$Small, [switch]$PassThru)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo 'out/vda-oracle-env/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'The prepared local Python environment is missing.' }
$mode = if ($Small -and $Vfg) { 'B-small-vfg' } elseif ($Vfg) { 'B-vfg' } elseif ($Small) { 'A-small' } else { 'A-baseline' }
$run = Join-Path $repo ('out/vfg-comparison/' + (Get-Date -Format 'yyyyMMdd-HHmmss-ffff') + '-' + $mode)
New-Item -ItemType Directory -Path (Split-Path $run -Parent) -Force | Out-Null
$priorPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = (@('v1','experiments/vfg','out/gui-python-deps','out/capture-python-deps','out/v1-python-deps') | ForEach-Object { Join-Path $repo $_ }) -join ';'
    $entry = Join-Path $repo 'experiments/vfg/compare_desktop.py'
    $arguments = @('"{0}"' -f $entry) + @('--output', ('"{0}"' -f $run))
    if ($Vfg) { $arguments += '--vfg' }
    if ($Small) { $arguments += @('--model', 'da2-small') }
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput ($run + '.stdout.log') -RedirectStandardError ($run + '.stderr.log')
    if ($PassThru) { $process }
} finally { $env:PYTHONPATH = $priorPythonPath }
