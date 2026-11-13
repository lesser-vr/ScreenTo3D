[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$SourcePath,
    [ValidateSet('performance', 'balanced', 'video-quality', 'offline-quality')]
    [string]$Mode = 'performance',
    [ValidateRange(30, 86400)] [int]$TimeoutSeconds = 900,
    [switch]$GpuPreview,
    [ValidateSet('h264', 'hevc')] [string]$OutputCodec = 'h264'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'process-tree-memory.ps1')
$sourceVideo = (Resolve-Path -LiteralPath $SourcePath).Path
$package = Join-Path $repoRoot 'out/release/ScreenTo3D'
$exe = Join-Path $package 'ScreenTo3D.exe'
if ($OutputCodec -ne 'h264' -and -not $GpuPreview) { throw 'HEVC soak requires the updated GPU preview package.' }
if ($GpuPreview) {
    $package = Join-Path $repoRoot 'out/gpu-preview/ScreenTo3D-GPU-Preview'
    $exe = Join-Path $package 'ScreenTo3D-GPU-Preview.exe'
}
$probe = Join-Path $package '_internal/ffmpeg/ffprobe.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Build the portable package first.' }
if (-not (Test-Path -LiteralPath $probe)) { throw 'Bundled ffprobe is missing.' }
$runRoot = Join-Path $repoRoot ('out/soak/' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$statusPath = Join-Path $runRoot 'events.jsonl'
$outputPath = Join-Path $runRoot 'output.mp4'
$csvPath = Join-Path $runRoot 'worker-memory.csv'
$treeCsvPath = Join-Path $runRoot 'process-tree-memory.csv'
$treeTotalsPath = Join-Path $runRoot 'process-tree-totals.csv'
$treeWriter = $treeTotalsWriter = $null
$treeSamples = $treeErrors = $treeMissingRoot = $treePeakProcesses = $treePeakDescendants = 0
$treePeakPrivate = $treeLastPrivate = $treePeakChildPrivate = 0L
$treeBaselinePrivate = $null
function Read-Probe([string]$Path) {
    $raw = & $probe -v error -show_streams -show_format -of json $Path
    if ($LASTEXITCODE -ne 0) { throw 'ffprobe failed.' }
    return $raw | ConvertFrom-Json
}
$inputProbe = Read-Probe $sourceVideo
$inputVideo = $inputProbe.streams | Where-Object codec_type -eq video | Select-Object -First 1
$writer = $null
$process = $null
$samples = 0
$peakPrivate = 0L
$baselinePrivate = $null
$lastPrivate = $null
$timer = [Diagnostics.Stopwatch]::StartNew()
try {
    $writer = [IO.StreamWriter]::new($csvPath, $false)
    $treeWriter = [IO.StreamWriter]::new($treeCsvPath, $false)
    $treeTotalsWriter = [IO.StreamWriter]::new($treeTotalsPath, $false)
    $treeWriter.WriteLine('sample_id,elapsed_seconds,pid,parent_pid,name,created_utc,private_bytes,working_set_bytes')
    $treeTotalsWriter.WriteLine('sample_id,elapsed_seconds,state,private_bytes,descendant_private_bytes,process_count,error_kind')
    $writer.WriteLine('elapsed_seconds,private_bytes,working_set_bytes')
    $arguments = "--worker --input `"$sourceVideo`" --output `"$outputPath`" --mode $Mode --status-file `"$statusPath`""
    if ($GpuPreview) { $arguments += " --output-codec $OutputCodec" }
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
        $snapshotSeconds = $timer.Elapsed.TotalSeconds.ToString('F3', [Globalization.CultureInfo]::InvariantCulture)
        $snapshotId = $samples + 1
        try {
            $rows = @(Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name,CreationDate,PrivatePageCount,WorkingSetSize -ErrorAction Stop)
            $tree = @(Select-WorkerProcessTree -Rows $rows -RootId $process.Id -RootStartedUtc $process.StartTime.ToUniversalTime())
            if ($tree.Count -eq 0) {
                $treeMissingRoot++
                $treeTotalsWriter.WriteLine("$snapshotId,$snapshotSeconds,missing_root,,,,")
            } else {
                $treeTotal = 0L
                $childTotal = 0L
                foreach ($member in $tree) {
                    if ($null -eq $member.PrivatePageCount -or $null -eq $member.WorkingSetSize) { throw 'Memory values unavailable' }
                    $treeTotal += [long]$member.PrivatePageCount
                    if ([int]$member.ProcessId -ne $process.Id) { $childTotal += [long]$member.PrivatePageCount }
                    $record = [pscustomobject][ordered]@{
                        sample_id = $snapshotId
                        elapsed_seconds = $snapshotSeconds
                        pid = $member.ProcessId; parent_pid = $member.ParentProcessId; name = $member.Name
                        created_utc = $member.CreationDate.ToUniversalTime().ToString('o')
                        private_bytes = $member.PrivatePageCount; working_set_bytes = $member.WorkingSetSize
                    }
                    $treeWriter.WriteLine(($record | ConvertTo-Csv -NoTypeInformation | Select-Object -Skip 1))
                }
                $treeSamples++
                $treeLastPrivate = $treeTotal
                $treePeakPrivate = [Math]::Max($treePeakPrivate, $treeTotal)
                $treePeakChildPrivate = [Math]::Max($treePeakChildPrivate, $childTotal)
                $treePeakProcesses = [Math]::Max($treePeakProcesses, $tree.Count)
                $treePeakDescendants = [Math]::Max($treePeakDescendants, $tree.Count - 1)
                if ($null -eq $treeBaselinePrivate -and $timer.Elapsed.TotalSeconds -ge 10) { $treeBaselinePrivate = $treeTotal }
                $treeTotalsWriter.WriteLine("$snapshotId,$snapshotSeconds,observed,$treeTotal,$childTotal,$($tree.Count),")
            }
            $treeWriter.Flush()
        } catch {
            $treeErrors++
            $treeTotalsWriter.WriteLine("$snapshotId,$snapshotSeconds,error,,,,$($_.Exception.GetType().Name)")
        }
        $treeTotalsWriter.Flush()
        $samples++
        Start-Sleep -Milliseconds 1000
    }
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "Worker failed: $($process.ExitCode)" }
} finally {
    foreach ($streamWriter in @($writer, $treeWriter, $treeTotalsWriter)) {
        if ($null -ne $streamWriter) { $streamWriter.Dispose() }
    }
    if ($null -ne $process -and -not $process.HasExited) {
        & taskkill /PID $process.Id /T /F | Out-Null
    }
}
$complete = Get-Content -LiteralPath $statusPath | ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object event -eq complete | Select-Object -Last 1
if (-not $complete -or $samples -eq 0) { throw 'Missing completion or memory samples.' }
if ($GpuPreview) {
    $stereo = $complete.telemetry.stereo
    if ($stereo.algorithm -ne 'forward_zbuffer_cuda_preview' -or
        $stereo.projection_resources.completed_eye_calls -ne (2 * $complete.frames) -or
        $stereo.projection_resources.zero_copy -ne $false -or
        $null -ne $complete.telemetry.diagnostic_hashes) {
        throw 'GPU preview projection accounting failed.'
    }
}
$outputProbe = Read-Probe $outputPath
$video = $outputProbe.streams | Where-Object codec_type -eq video | Select-Object -First 1
if ($video.codec_name -ne $OutputCodec) { throw 'Output codec contract failed.' }
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
    schema_version = 2
    gpu_preview = [bool]$GpuPreview
    output_codec = $OutputCodec
    executable_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    source_commit = (& git -C $repoRoot rev-parse HEAD).Trim()
    source_dirty = [bool](& git -C $repoRoot status --porcelain)
    package = Get-Content (Join-Path $package 'build-manifest.json') -Raw | ConvertFrom-Json
    input_sha256 = (Get-FileHash -LiteralPath $sourceVideo -Algorithm SHA256).Hash
    input_probe = $inputProbe
    output_probe = $outputProbe
    completion = $complete
    process_tree_memory = [ordered]@{
        scope = 'root_and_descendants_present_in_snapshot'
        source = 'Win32_Process_PrivatePageCount_WorkingSetSize'
        sample_count = $treeSamples; observation_errors = $treeErrors; missing_root_snapshots = $treeMissingRoot
        sampled_max_process_count = $treePeakProcesses; sampled_max_descendant_count = $treePeakDescendants
        sampled_max_private_bytes = $(if ($treeSamples) { $treePeakPrivate } else { $null })
        sampled_max_descendant_private_bytes = $(if ($treeSamples) { $treePeakChildPrivate } else { $null })
        first_post_10s_private_bytes = $treeBaselinePrivate
        last_private_bytes = $(if ($treeSamples) { $treeLastPrivate } else { $null })
        leak_verdict = 'not_established_by_single_run'
        csv = $treeCsvPath
        totals_csv = $treeTotalsPath
        timestamp_tolerance_microseconds = 1
        coverage = $(if (-not $treeSamples) { 'unavailable' } elseif ($treeErrors -or $treeMissingRoot) { 'partial' } else { 'sampled_not_exhaustive' })
    }
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
