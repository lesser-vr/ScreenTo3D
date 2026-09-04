[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$SourcePath,
    [ValidateSet('performance', 'balanced', 'video-quality', 'offline-quality')]
    [string]$Mode = 'performance',
    [ValidateRange(30, 86400)] [int]$TimeoutSeconds = 900
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceVideo = (Resolve-Path -LiteralPath $SourcePath).Path
$package = Join-Path $repoRoot 'out/release/DepthSBS'
$exe = Join-Path $package 'DepthSBS.exe'
$probe = Join-Path $package '_internal/ffmpeg/ffprobe.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Build the portable package first.' }
if (-not (Test-Path -LiteralPath $probe)) { throw 'Bundled ffprobe is missing.' }
$runRoot = Join-Path $repoRoot ('out/soak/' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$statusPath = Join-Path $runRoot 'events.jsonl'
$outputPath = Join-Path $runRoot 'output.mp4'
$csvPath = Join-Path $runRoot 'worker-memory.csv'
function Read-Probe([string]$Path) {
    $raw = & $probe -v error -show_streams -show_format -of json $Path
    if ($LASTEXITCODE -ne 0) { throw 'ffprobe failed.' }
    return $raw | ConvertFrom-Json
}
$inputProbe = Read-Probe $sourceVideo
$inputVideo = $inputProbe.streams | Where-Object codec_type -eq video | Select-Object -First 1
$writer = [IO.StreamWriter]::new($csvPath, $false)
$process = $null
$samples = 0
$peakPrivate = 0L
$baselinePrivate = $null
$lastPrivate = $null
$timer = [Diagnostics.Stopwatch]::StartNew()
try {
    $writer.WriteLine('elapsed_seconds,private_bytes,working_set_bytes')
    $arguments = "--worker --input `"$sourceVideo`" --output `"$outputPath`" --mode $Mode --status-file `"$statusPath`""
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru -WindowStyle Hidden
    while (-not $process.HasExited) {
        if ($timer.Elapsed.TotalSeconds -gt $TimeoutSeconds) { throw 'Worker timeout.' }
        $process.Refresh()
        if ($process.HasExited) { break }
        $lastPrivate = $process.PrivateMemorySize64
        $workingSet = $process.WorkingSet64
        $seconds = $timer.Elapsed.TotalSeconds
        $peakPrivate = [Math]::Max($peakPrivate, $lastPrivate)
        if ($null -eq $baselinePrivate -and $seconds -ge 10) { $baselinePrivate = $lastPrivate }
        $writer.WriteLine([string]::Format([Globalization.CultureInfo]::InvariantCulture,
            '{0:F3},{1},{2}', $seconds, $lastPrivate, $workingSet))
        $writer.Flush()
        $samples++
        Start-Sleep -Milliseconds 1000
    }
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "Worker failed: $($process.ExitCode)" }
} finally {
    $writer.Dispose()
    if ($null -ne $process -and -not $process.HasExited) {
        & taskkill /PID $process.Id /T /F | Out-Null
    }
}
$complete = Get-Content -LiteralPath $statusPath | ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object event -eq complete | Select-Object -Last 1
if (-not $complete -or $samples -eq 0) { throw 'Missing completion or memory samples.' }
$outputProbe = Read-Probe $outputPath
$video = $outputProbe.streams | Where-Object codec_type -eq video | Select-Object -First 1
if ([long]$video.nb_frames -ne [long]$inputVideo.nb_frames -or
    [long]$complete.frames -ne [long]$inputVideo.nb_frames -or
    [int]$video.width -ne ([int]$inputVideo.width * 2) -or
    [int]$video.height -ne [int]$inputVideo.height -or
    @($outputProbe.streams | Where-Object codec_type -eq audio).Count -ne
    @($inputProbe.streams | Where-Object codec_type -eq audio).Count) { throw 'Output contract failed.' }
$requiredStages = @('engine_startup', 'pipeline_setup', 'frame_loop', 'decode_drain',
    'encode_drain', 'resource_snapshot', 'backend_close', 'audio_mux', 'publish')
$life = $complete.telemetry.lifecycle_seconds
foreach ($stage in $requiredStages) {
    if ($null -eq $life.$stage -or $life.$stage -lt 0) { throw "Missing/invalid lifecycle stage: $stage" }
}
$lifecycleTotal = ($life.PSObject.Properties.Value | Measure-Object -Sum).Sum
if ($lifecycleTotal -gt ($complete.elapsed_seconds + 0.001) -or
    $complete.telemetry.job_elapsed_seconds -lt $complete.elapsed_seconds -or
    $null -eq $complete.telemetry.stages.frame_total -or
    $complete.telemetry.stages.frame_total.count -ne $complete.frames) {
    throw 'Lifecycle or frame-count accounting failed.'
}
foreach ($stage in $complete.telemetry.stages.PSObject.Properties) {
    if ($stage.Value.sample_count -ne [Math]::Min($stage.Value.count, $complete.telemetry.sample_capacity)) {
        throw "Sample cap contract failed: $($stage.Name)"
    }
}
$artifact = [ordered]@{
    schema_version = 1
    source_commit = (& git -C $repoRoot rev-parse HEAD).Trim()
    source_dirty = [bool](& git -C $repoRoot status --porcelain)
    package = Get-Content (Join-Path $package 'build-manifest.json') -Raw | ConvertFrom-Json
    input_sha256 = (Get-FileHash -LiteralPath $sourceVideo -Algorithm SHA256).Hash
    input_probe = $inputProbe
    output_probe = $outputProbe
    completion = $complete
    worker_memory = [ordered]@{
        scope = 'worker_process_only_not_ffmpeg_children'
        sample_count = $samples
        sampled_max_private_bytes = $peakPrivate
        first_post_10s_private_bytes = $baselinePrivate
        last_sample_private_bytes = $lastPrivate
        post_10s_to_last_delta_bytes = $(if ($null -ne $baselinePrivate) { $lastPrivate - $baselinePrivate } else { $null })
        leak_verdict = 'not_established_by_single_run'
        csv = $csvPath
    }
}
$artifactPath = Join-Path $runRoot 'result.json'
$artifact | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $artifactPath -Encoding UTF8
$artifact.worker_memory | ConvertTo-Json
Write-Output $artifactPath
