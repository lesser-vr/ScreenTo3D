[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $repoRoot 'out\models\da2-small'
$enginePath = Join-Path $outputRoot 'da2-small-518.plan'
$inputPath = Join-Path $outputRoot 'gradient-input-fp32.raw'
$outputPath = Join-Path $outputRoot 'gradient-depth.json'
$logPath = Join-Path $outputRoot 'inference.log'
$toolPath = Join-Path $repoRoot 'tools\da2-small-inference-smoke.py'
$relativeInputPath = 'out\models\da2-small\gradient-input-fp32.raw'

if (-not (Test-Path $enginePath)) {
    powershell -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $PSScriptRoot 'da2-small-engine-smoke.ps1') | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'DA2 Small engine preparation failed.' }
}

python $toolPath generate $inputPath
if ($LASTEXITCODE -ne 0) { throw 'DA2 Small deterministic input generation failed.' }

$tensorRt = powershell -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $PSScriptRoot 'tensorrt-check.ps1') | ConvertFrom-Json
if (-not $tensorRt.available) { throw 'TensorRT validation failed.' }
$env:Path = "$($tensorRt.bin);$env:Path"
$trtexec = Join-Path $tensorRt.bin 'trtexec.exe'
$arguments = @(
    "--loadEngine=$enginePath"
    '--shapes=pixel_values:1x3x518x518'
    "--loadInputs=pixel_values:$relativeInputPath"
    '--iterations=1'
    '--warmUp=0'
    '--duration=0'
    "--exportOutput=$outputPath"
)

$previousLocation = Get-Location
Set-Location $repoRoot
try {
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $trtexec @arguments 2>&1 | Tee-Object -FilePath $logPath | Out-Null
    $nativeExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorAction
} finally {
    Set-Location $previousLocation
}
if ($nativeExitCode -ne 0) { throw 'DA2 Small TensorRT inference failed.' }

python $toolPath validate $outputPath
if ($LASTEXITCODE -ne 0) { throw 'DA2 Small output validation failed.' }
