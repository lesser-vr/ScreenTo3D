[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $repoRoot 'out\models\da2-small'
$manifest = Get-Content `
    (Join-Path $repoRoot 'models\da2-small\fp32-reference-manifest.json') `
    -Raw | ConvertFrom-Json
$modelPath = Join-Path $outputRoot 'model_fp32.onnx'
$partialPath = "$modelPath.partial"
$modelUrl = "https://huggingface.co/$($manifest.repository)/resolve/$($manifest.revision)/$($manifest.path)"
$pythonDependencies = Join-Path $repoRoot 'out\python-deps'

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
if (-not (Test-Path $modelPath)) {
    curl.exe -L --fail --show-error --output $partialPath $modelUrl
    if ($LASTEXITCODE -ne 0) { throw 'DA2 Small FP32 reference download failed.' }
    Move-Item $partialPath $modelPath -Force
}
if ((Get-Item $modelPath).Length -ne [long]$manifest.bytes) {
    throw 'DA2 Small FP32 reference size mismatch.'
}
$actualHash = (Get-FileHash $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $manifest.sha256) {
    throw "DA2 Small FP32 reference SHA-256 mismatch: $actualHash"
}
if (-not (Test-Path (Join-Path $pythonDependencies 'onnxruntime'))) {
    throw 'Install reference dependencies with: python -m pip install --target out\python-deps -r tools\requirements-reference.txt'
}

powershell -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $PSScriptRoot 'da2-small-inference-smoke.ps1') | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'DA2 Small TensorRT inference smoke failed.' }

$env:PYTHONPATH = $pythonDependencies
python (Join-Path $repoRoot 'tools\da2-small-reference-check.py') `
    $modelPath `
    (Join-Path $outputRoot 'gradient-input-fp32.raw') `
    (Join-Path $outputRoot 'gradient-depth.json')
if ($LASTEXITCODE -ne 0) { throw 'DA2 Small FP32 reference comparison failed.' }
