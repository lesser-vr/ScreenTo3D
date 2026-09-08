[CmdletBinding()]
param([Parameter(Mandatory = $true)] [string]$FixtureRoot)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$fixture = (Resolve-Path -LiteralPath $FixtureRoot).Path
$manifest = Get-Content -LiteralPath (Join-Path $fixture 'manifest.json') -Raw | ConvertFrom-Json
if ($manifest.frames -ne 48 -or $manifest.fps -ne 24 -or $manifest.width -ne 640 -or
    $manifest.height -ne 360 -or $manifest.cut_frame_zero_based -ne 25) {
    throw 'Use the deterministic two-second motion fixture.'
}
$source = Join-Path $fixture 'motion-h264.mp4'
$runRoot = Join-Path $repoRoot ('out/motion-stability/' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runRoot | Out-Null
$longSource = Join-Path $runRoot 'motion-30s.mp4'
$ffmpeg = Join-Path $repoRoot 'out/release/DepthSBS/_internal/ffmpeg/ffmpeg.exe'
& $ffmpeg -n -v error -stream_loop 14 -i $source -map 0:v:0 -vf fps=24 -frames:v 720 `
    -an -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p $longSource
if ($LASTEXITCODE -ne 0) { throw 'CFR stability fixture generation failed.' }
$soakLines = @(& (Join-Path $PSScriptRoot 'soak-v1.ps1') -SourcePath $longSource -Mode performance)
$soakPath = [string]$soakLines[-1]
$soak = Get-Content -LiteralPath $soakPath -Raw | ConvertFrom-Json
$t = $soak.completion.telemetry
if ($soak.completion.frames -ne 720 -or $t.scene_cut_resets -ne 29 -or
    $t.extra_cut_inferences -ne 15 -or $t.extra_motion_inferences -ne 345 -or
    $t.resources.cuda_counters.completed_inferences -ne 720 -or
    $t.stages.temporal_guard.count -ne 720) {
    throw "Continuous motion/cut accounting failed: $soakPath"
}
Write-Host 'PASS: continuous 720 frames, 29 cuts, 720 inferences'
$cleanupLines = @(& (Join-Path $PSScriptRoot 'test-v1-cleanup.ps1') -SourcePath $source -Runs 3)
$cleanupPath = [string]$cleanupLines[-1]
$cleanup = Get-Content -LiteralPath $cleanupPath -Raw | ConvertFrom-Json
if (@($cleanup.observations).Count -ne 12 -or @($cleanup.observations | Where-Object { -not $_.passed }).Count) {
    throw 'Expected 12 passing same-process lifecycle scenarios.'
}
Write-Host 'PASS: three success/cancel/inference-error/invalid-input cycles'
$cancelLines = @(& (Join-Path $PSScriptRoot 'test-v1-cancel.ps1') -SourcePath $longSource)
$cancelRoot = [string]$cancelLines[-1]
Write-Host 'PASS: packaged cancellation and prior-output preservation'
$resultPath = Join-Path $runRoot 'validation.json'
[ordered]@{
    continuous_result = $soakPath
    lifecycle_result = $cleanupPath
    packaged_cancel_directory = $cancelRoot
    passed = $true
    scope = '30-second CFR fixture, three lifecycle cycles, one packaged cancel; not a leak-free proof'
} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Output $resultPath
