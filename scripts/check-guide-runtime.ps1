# Real model, native ownership and application checks for the guide candidate.
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$env:PYTHONPATH='v1;experiments/zipdepth;experiments/vfg;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps'
$python=Join-Path $repoRoot 'out/vda-oracle-env/Scripts/python.exe'
$checks=@(
    @{name='small-quality';argv=@('experiments/zipdepth/check_guide_precision.py','--candidate','guide-compensated','--public','--tag','final','--model','small')},
    @{name='geometry';argv=@('v1/check_stereo_geometry_gpu.py','--output','out/guide-compensated/geometry.json')},
    @{name='small-runtime';argv=@('v1/test_small_gpu_input.py','--quality','detail','--output','out/guide-compensated/small-validation')},
    @{name='vfg';argv=@('v1/check_vfg_option.py','--output','out/guide-compensated/vfg-validation')}
)
foreach($check in $checks) {
    Write-Output "Checking $($check.name)"
    $testArgs=$check.argv
    & $python @testArgs *> "out/guide-compensated/$($check.name).log"
    if($LASTEXITCODE -ne 0) {throw "Guide regression failed: $($check.name)"}
}
