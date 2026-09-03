[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [Alias('Input')]
    [string]$SourcePath,
    [ValidateSet('performance', 'balanced', 'video-quality', 'offline-quality')]
    [string]$Mode = 'performance',
    [ValidateRange(1, 20)] [int]$Runs = 5,
    [ValidateRange(0, 5)] [int]$WarmupRuns = 1
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceVideo = (Resolve-Path $SourcePath).Path
$executable = Join-Path $repoRoot 'out\release\DepthSBS\DepthSBS.exe'
$packageManifestPath = Join-Path $repoRoot 'out\release\DepthSBS\build-manifest.json'
$benchmarkRoot = Join-Path $repoRoot 'out\benchmarks'
if (-not (Test-Path $executable)) { throw 'Build the V1 portable package first.' }
if (-not (Test-Path $packageManifestPath)) { throw 'Package build manifest is missing.' }
New-Item -ItemType Directory -Path $benchmarkRoot -Force | Out-Null

function Read-Probe([string]$MediaPath) {
    $raw = & ffprobe -v error -print_format json -show_streams -show_format $MediaPath
    if ($LASTEXITCODE -ne 0) { throw "FFprobe failed for $MediaPath" }
    return $raw | ConvertFrom-Json
}

function Find-Video($Probe) {
    return $Probe.streams | Where-Object codec_type -eq 'video' | Select-Object -First 1
}

function Count-Audio($Probe) {
    return @($Probe.streams | Where-Object codec_type -eq 'audio').Count
}

$sourceProbe = Read-Probe $sourceVideo
$sourceStream = Find-Video $sourceProbe
$packageManifest = Get-Content $packageManifestPath -Raw | ConvertFrom-Json
$gpuFields = ((& nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap `
    --format=csv,noheader,nounits | Select-Object -First 1) -split ',\s*')
$samples = @()

for ($index = 0; $index -lt ($WarmupRuns + $Runs); $index++) {
    $kind = if ($index -lt $WarmupRuns) { 'warmup' } else { 'measured' }
    $number = if ($kind -eq 'warmup') { $index + 1 } else { $index - $WarmupRuns + 1 }
    $stem = "v1-$Mode-$kind-$number-$([Guid]::NewGuid().ToString('N'))"
    $statusPath = Join-Path $benchmarkRoot "$stem.jsonl"
    $outputPath = Join-Path $benchmarkRoot "$stem.mp4"
    $arguments = "--worker --input `"$sourceVideo`" --output `"$outputPath`" --mode $Mode --status-file `"$statusPath`""
    $process = Start-Process -FilePath $executable -ArgumentList $arguments `
        -PassThru -Wait -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "Benchmark $kind run $number failed." }
    $events = Get-Content $statusPath | ForEach-Object { $_ | ConvertFrom-Json }
    $complete = $events | Where-Object event -eq 'complete' | Select-Object -Last 1
    if (-not $complete) { throw "Benchmark $kind run $number has no completion event." }
    $outputProbe = Read-Probe $outputPath
    $outputStream = Find-Video $outputProbe
    if ([int]$outputStream.width -ne ([int]$sourceStream.width * 2) -or
        [int]$outputStream.height -ne [int]$sourceStream.height -or
        [int]$outputStream.nb_frames -ne [int]$sourceStream.nb_frames -or
        (Count-Audio $outputProbe) -ne (Count-Audio $sourceProbe)) {
        throw "Output contract failed for $kind run $number."
    }
    $samples += [pscustomobject]@{
        kind = $kind
        run = $number
        elapsed_seconds = [double]$complete.elapsed_seconds
        processing_fps = [double]$complete.processing_fps
        frames = [int]$complete.frames
        output_bytes = (Get-Item $outputPath).Length
        policy = $complete.policy
        status_file = $statusPath
        output_file = $outputPath
    }
}

$measured = @($samples | Where-Object kind -eq 'measured')
function Get-Median([double[]]$Values) {
    $ordered = @($Values | Sort-Object)
    $middle = [int][Math]::Floor($ordered.Count / 2)
    if ($ordered.Count % 2) { return $ordered[$middle] }
    return ($ordered[$middle - 1] + $ordered[$middle]) / 2
}
$fpsValues = [double[]]$measured.processing_fps
$elapsedValues = [double[]]$measured.elapsed_seconds
$artifactPath = Join-Path $benchmarkRoot "v1-$Mode-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')).json"
$artifact = [ordered]@{
    schema_version = 1
    created_at_utc = [DateTime]::UtcNow.ToString('o')
    source = [ordered]@{
        commit = (& git -C $repoRoot rev-parse HEAD).Trim()
        branch = (& git -C $repoRoot branch --show-current).Trim()
        dirty = [bool](& git -C $repoRoot status --porcelain)
    }
    os = [Environment]::OSVersion.VersionString
    gpu = [ordered]@{
        name = $gpuFields[0]; driver = $gpuFields[1]
        memory_mib = [int]$gpuFields[2]; compute_capability = $gpuFields[3]
    }
    package = $packageManifest
    input = [ordered]@{
        path = $sourceVideo
        sha256 = (Get-FileHash $sourceVideo -Algorithm SHA256).Hash.ToLowerInvariant()
        bytes = (Get-Item $sourceVideo).Length
        probe = $sourceProbe
    }
    mode = $Mode
    warmup_runs = $WarmupRuns
    measured_runs = $Runs
    runs = $samples
    aggregate = [ordered]@{
        processing_fps_median = Get-Median $fpsValues
        processing_fps_min = ($fpsValues | Measure-Object -Minimum).Minimum
        processing_fps_max = ($fpsValues | Measure-Object -Maximum).Maximum
        elapsed_seconds_median = Get-Median $elapsedValues
        elapsed_seconds_min = ($elapsedValues | Measure-Object -Minimum).Minimum
        elapsed_seconds_max = ($elapsedValues | Measure-Object -Maximum).Maximum
    }
}
$artifact | ConvertTo-Json -Depth 20 | Set-Content $artifactPath -Encoding UTF8
$artifact.aggregate | ConvertTo-Json
Write-Output $artifactPath
