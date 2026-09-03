[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Release'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $repoRoot 'out\media-smoke'
$inputPath = Join-Path $outputRoot 'fixture-720p30.mp4'
$temporaryOutputPath = Join-Path $outputRoot 'fixture-sbs.mp4.partial'
$finalOutputPath = Join-Path $outputRoot 'fixture-sbs.mp4'
$reportPath = Join-Path $outputRoot 'report.json'

$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
$ffprobe = (Get-Command ffprobe -ErrorAction Stop).Source

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

function Invoke-Checked {
    param(
        [Parameter(Mandatory)]
        [string]$Executable,
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $Executable"
    }
}

# The reference fixture has moving geometry, a hard cut at one second, and audio.
# It is generated locally so tests do not depend on copyrighted media.
Invoke-Checked $ffmpeg @(
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'lavfi', '-i',
    'testsrc2=size=1280x720:rate=30:duration=1,drawtext=text=SHOT_A:x=40:y=40:fontsize=48:fontcolor=white',
    '-f', 'lavfi', '-i',
    'smptebars=size=1280x720:rate=30:duration=1,drawtext=text=SHOT_B:x=40:y=40:fontsize=48:fontcolor=white',
    '-f', 'lavfi', '-i', 'sine=frequency=1000:sample_rate=48000:duration=2',
    '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]',
    '-map', '[v]', '-map', '2:a:0',
    '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
    '-g', '30', '-c:a', 'aac', '-b:a', '128k', '-shortest',
    $inputPath
)

# This intentionally uses a simple deterministic duplicate-eye reference. It is
# a media/timestamp oracle, not the future depth-based or zero-copy implementation.
Invoke-Checked $ffmpeg @(
    '-hide_banner', '-loglevel', 'error', '-y',
    '-i', $inputPath,
    '-filter_complex', '[0:v]split=2[left][right];[left][right]hstack=inputs=2[sbs]',
    '-map', '[sbs]', '-map', '0:a:0?',
    '-c:v', 'h264_nvenc', '-preset', 'p4', '-pix_fmt', 'yuv420p',
    '-c:a', 'copy', '-movflags', '+faststart',
    '-f', 'mp4', $temporaryOutputPath
)

$probeJson = & $ffprobe @(
    '-v', 'error', '-show_streams', '-show_format', '-count_frames',
    '-of', 'json', $temporaryOutputPath
)
if ($LASTEXITCODE -ne 0) { throw 'ffprobe failed for the generated SBS output.' }

$probe = $probeJson | ConvertFrom-Json
$video = @($probe.streams | Where-Object codec_type -eq 'video')
$audio = @($probe.streams | Where-Object codec_type -eq 'audio')

if ($video.Count -ne 1) { throw "Expected one video stream, found $($video.Count)." }
if ($audio.Count -ne 1) { throw "Expected one audio stream, found $($audio.Count)." }
if ($video[0].width -ne 2560 -or $video[0].height -ne 720) {
    throw "Unexpected SBS dimensions: $($video[0].width)x$($video[0].height)."
}
if ([int]$video[0].nb_read_frames -ne 60) {
    throw "Expected 60 decoded frames, found $($video[0].nb_read_frames)."
}
if ([double]$probe.format.duration -lt 1.95 -or [double]$probe.format.duration -gt 2.10) {
    throw "Unexpected output duration: $($probe.format.duration)."
}

$report = [ordered]@{
    schema_version = 1
    reference_only = $true
    input = [ordered]@{
        path = $inputPath
        width = 1280
        height = 720
        fps = 30
        expected_frames = 60
    }
    output = [ordered]@{
        path = $finalOutputPath
        codec = $video[0].codec_name
        width = [int]$video[0].width
        height = [int]$video[0].height
        frames = [int]$video[0].nb_read_frames
        duration_seconds = [double]$probe.format.duration
        audio_codec = $audio[0].codec_name
    }
    invariants = [ordered]@{
        doubled_width = $true
        preserved_height = $true
        preserved_frame_count = $true
        preserved_audio_stream = $true
        atomic_publication = $true
    }
}

$report | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $reportPath
Move-Item -LiteralPath $temporaryOutputPath -Destination $finalOutputPath -Force

Write-Output "Media smoke test passed."
Write-Output "Output: $finalOutputPath"
Write-Output "Report: $reportPath"
