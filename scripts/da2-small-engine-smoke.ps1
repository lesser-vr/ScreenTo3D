[CmdletBinding()]
param(
    [switch]$ForceDownload
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repoRoot 'models\da2-small\model-manifest.json'
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$outputRoot = Join-Path $repoRoot 'out\models\da2-small'
$modelPath = Join-Path $outputRoot 'model_fp16.onnx'
$enginePath = Join-Path $outputRoot 'da2-small-518.plan'
$partialPath = "$modelPath.partial"
$modelUrl = "https://huggingface.co/$($manifest.onnx_repository)/resolve/$($manifest.onnx_revision)/$($manifest.onnx_path)"

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
if ($ForceDownload -or -not (Test-Path $modelPath)) {
    Remove-Item $partialPath -Force -ErrorAction SilentlyContinue
    curl.exe -L --fail --show-error --output $partialPath $modelUrl
    if ($LASTEXITCODE -ne 0) { throw 'DA2 Small ONNX download failed.' }
    Move-Item $partialPath $modelPath -Force
}

$model = Get-Item $modelPath
if ($model.Length -ne [long]$manifest.onnx_bytes) {
    throw "DA2 Small ONNX size mismatch: $($model.Length)"
}
$actualHash = (Get-FileHash $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $manifest.onnx_sha256) {
    throw "DA2 Small ONNX SHA-256 mismatch: $actualHash"
}

$tensorRt = powershell -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $PSScriptRoot 'tensorrt-check.ps1') | ConvertFrom-Json
if (-not $tensorRt.available) { throw 'TensorRT validation failed.' }
$env:TensorRT_PATH = $tensorRt.bin
$env:Path = "$($tensorRt.bin);$env:Path"
$trtexec = Join-Path $tensorRt.bin 'trtexec.exe'
$buildLog = Join-Path $outputRoot 'build.log'

$arguments = @(
    "--onnx=$modelPath"
    "--saveEngine=$enginePath"
    '--minShapes=pixel_values:1x3x518x518'
    '--optShapes=pixel_values:1x3x518x518'
    '--maxShapes=pixel_values:1x3x518x518'
    '--skipInference'
    '--memPoolSize=workspace:2048'
)
$started = [System.Diagnostics.Stopwatch]::StartNew()
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $trtexec @arguments 2>&1 | Tee-Object -FilePath $buildLog
$nativeExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorAction
if ($nativeExitCode -ne 0) { throw 'DA2 Small TensorRT engine build failed.' }
$started.Stop()
if (-not (Test-Path $enginePath)) { throw 'DA2 Small engine was not published.' }

$result = [ordered]@{
    schema_version = 1
    model_sha256 = $actualHash
    model_bytes = $model.Length
    engine = $enginePath
    engine_bytes = (Get-Item $enginePath).Length
    input_shape = @(1, 3, 518, 518)
    tensorrt_version = $tensorRt.version
    build_ms = $started.ElapsedMilliseconds
    engine_build_validated = $true
    inference_validated = $false
}
$result | ConvertTo-Json -Depth 4
