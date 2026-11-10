# Prepared-local GPU/runtime regression; only owned public source windows.
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$env:PYTHONPATH='v1;experiments/zipdepth;experiments/vfg;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps'
$python=Join-Path $repoRoot 'out/vda-oracle-env/Scripts/python.exe'
$checks=@(
    @{name='parity-layout';argv=@('experiments/zipdepth/check_gpu_opt.py')},
    @{name='geometry';argv=@('v1/check_stereo_geometry_gpu.py','--output','out/gpu-load-opt/geometry.json')},
    @{name='small';argv=@('v1/test_small_gpu_input.py','--quality','detail','--output','out/gpu-load-opt/small-validation')},
    @{name='vfg';argv=@('v1/check_vfg_option.py','--output','out/gpu-load-opt/vfg-validation')}
)
foreach($check in $checks) {
    Write-Output "Checking $($check.name)"
    $testArgs=$check.argv
    & $python @testArgs *> "out/gpu-load-opt/$($check.name).log"
    if($LASTEXITCODE -ne 0) {throw "GPU regression failed: $($check.name)"}
}
