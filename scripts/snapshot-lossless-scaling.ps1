[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [string]$InstallationDirectory = 'C:\Program Files (x86)\Steam\steamapps\common\Lossless Scaling',
    [string]$SettingsFile = "$env:LOCALAPPDATA\Lossless Scaling\Settings.xml"
)

$ErrorActionPreference = 'Stop'
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) {
    throw "Output directory already exists: $output"
}
$executable = Join-Path $InstallationDirectory 'LosslessScaling.exe'
$config = Join-Path $InstallationDirectory 'config.ini'
foreach ($file in @($executable, $config, $SettingsFile)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Required Lossless Scaling file is missing: $file"
    }
}

[xml]$settings = Get-Content -Raw -LiteralPath $SettingsFile
$profiles = @($settings.Settings.GameProfiles.Profile)
if ($profiles.Count -lt 1) {
    throw 'No Lossless Scaling game profile was found.'
}

function Profile-Value([object]$Profile, [string]$Name) {
    $value = $Profile.$Name
    if ($null -eq $value) { return $null }
    return [string]$value
}

$profileRecords = foreach ($profile in $profiles) {
    [ordered]@{
        title = Profile-Value $profile 'Title'
        scaling_type = Profile-Value $profile 'ScalingType'
        scaling_mode = Profile-Value $profile 'ScalingMode'
        scaling_fit_mode = Profile-Value $profile 'ScalingFitMode'
        frame_generation = Profile-Value $profile 'FrameGeneration'
        lsfg3_mode = Profile-Value $profile 'LSFG3Mode1'
        lsfg3_multiplier = Profile-Value $profile 'LSFG3Multiplier'
        lsfg3_target = Profile-Value $profile 'LSFG3Target'
        lsfg_flow_scale = Profile-Value $profile 'LSFGFlowScale'
        lsfg_size = Profile-Value $profile 'LSFGSize'
        capture_api = Profile-Value $profile 'CaptureApi'
        sync_mode = Profile-Value $profile 'SyncMode'
        max_frame_latency = Profile-Value $profile 'MaxFrameLatency'
        queue_target = Profile-Value $profile 'QueueTarget'
        gsync_support = Profile-Value $profile 'GsyncSupport'
        hdr_support = Profile-Value $profile 'HdrSupport'
        output_display_id = Profile-Value $profile 'OutputDisplayId'
        multi_display_mode = Profile-Value $profile 'MultiDisplayMode'
    }
}

$gpu = @()
try {
    $gpu = @(& nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>$null)
} catch {
    $gpu = @()
}
$power = $null
try {
    $power = (& powercfg /getactivescheme 2>$null | Out-String).Trim()
} catch {
    $power = $null
}

$version = (Get-Item -LiteralPath $executable).VersionInfo
$report = [ordered]@{
    schema = 'depthsbs.lossless-scaling-baseline-snapshot.v1'
    status = 'captured'
    captured_utc = [DateTime]::UtcNow.ToString('o')
    scope = 'Read-only installed baseline configuration; not proof that a profile was active during a capture.'
    executable = [ordered]@{
        product_version = $version.ProductVersion
        file_version = $version.FileVersion
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $executable).Hash.ToLowerInvariant()
    }
    settings = [ordered]@{
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $SettingsFile).Hash.ToLowerInvariant()
        profiles = @($profileRecords)
    }
    config = [ordered]@{
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $config).Hash.ToLowerInvariant()
    }
    environment = [ordered]@{
        gpu_and_driver = @($gpu)
        active_power_scheme = $power
    }
}

New-Item -ItemType Directory -Path $output | Out-Null
$reportPath = Join-Path $output 'report.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Output $reportPath
