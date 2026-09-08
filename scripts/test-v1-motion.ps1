[CmdletBinding()]
param([string]$FixtureRoot)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $FixtureRoot) {
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = "$(Join-Path $repoRoot 'out/v1-python-deps');$(Join-Path $repoRoot 'v1')"
        $FixtureRoot = & python (Join-Path $repoRoot 'v1/make_quality_fixtures.py')
        if ($LASTEXITCODE -ne 0) { throw 'Quality fixture generation failed.' }
    } finally { $env:PYTHONPATH = $previousPythonPath }
}
$FixtureRoot = (Resolve-Path -LiteralPath $FixtureRoot).Path
$results = @()
foreach ($codec in @('h264', 'hevc')) {
    foreach ($mode in @('performance', 'balanced', 'video-quality', 'offline-quality')) {
        $lines = @(& (Join-Path $PSScriptRoot 'soak-v1.ps1') -SourcePath (Join-Path $FixtureRoot "motion-$codec.mp4") -Mode $mode)
        $artifactPath = [string]$lines[-1]
        $artifact = Get-Content -LiteralPath $artifactPath -Raw | ConvertFrom-Json
        $complete = $artifact.completion
        $telemetry = $complete.telemetry
        $expectedExtra = if ($mode -eq 'performance') { 1 } else { 0 }
        $expectedInferences = 48
        $expectedMotion = if ($mode -eq 'performance') { 23 } else { 0 }
        if ($complete.frames -ne 48 -or $telemetry.scene_cut_resets -ne 1 -or
            $telemetry.extra_cut_inferences -ne $expectedExtra -or
            $telemetry.extra_motion_inferences -ne $expectedMotion -or
            $telemetry.resources.cuda_counters.completed_inferences -ne $expectedInferences -or
            $telemetry.stereo.flat_background_frames -ne 0) {
            throw "Motion/cut gate failed: $codec $mode. See $artifactPath"
        }
        $results += [ordered]@{ codec = $codec; mode = $mode; passed = $true; artifact = $artifactPath }
        Write-Host "PASS: $codec $mode, 48 frames, one cut, $expectedInferences inferences"
    }
}
$report = Join-Path $FixtureRoot ('validation-' + [Guid]::NewGuid().ToString('N') + '.json')
$results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $report -Encoding UTF8
Write-Output $report
