[CmdletBinding()]
param([string]$SourcePath = 'out/media-smoke/soak-cfr-720p30-300s.mp4')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceVideo = (Resolve-Path $SourcePath).Path
$exe = Join-Path $repoRoot 'out/release/ScreenTo3D/ScreenTo3D.exe'
$runRoot = Join-Path $repoRoot ('out/cleanup/package-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$statusPath = Join-Path $runRoot 'events.jsonl'
$cancelPath = Join-Path $runRoot 'cancel.token'
$outputPath = Join-Path $runRoot 'output.mp4'
# Seed a prior output to ensure cancellation cannot destroy it.
Copy-Item -LiteralPath $sourceVideo -Destination $outputPath
$priorHash = (Get-FileHash -LiteralPath $outputPath).Hash
$arguments = "--worker --input `"$sourceVideo`" --output `"$outputPath`" --mode performance --status-file `"$statusPath`" --cancel-file `"$cancelPath`""
$process = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru -WindowStyle Hidden
$timer = [Diagnostics.Stopwatch]::StartNew()
$requested = $false
try {
    while (-not $process.HasExited) {
        if ($timer.Elapsed.TotalSeconds -gt 30) { throw 'Cancellation timed out.' }
        if (-not $requested -and (Test-Path -LiteralPath $statusPath)) {
            if (Select-String -LiteralPath $statusPath -Pattern '"event": "progress"' -Quiet) {
                New-Item -ItemType File -Path $cancelPath | Out-Null
                $requested = $true
            }
        }
        Start-Sleep -Milliseconds 100
    }
    $process.WaitForExit()
    if (-not $requested -or $process.ExitCode -ne 2) { throw "Unexpected cancellation exit: $($process.ExitCode)" }
} finally {
    if (-not $process.HasExited) { & taskkill /PID $process.Id /T /F | Out-Null }
}
$newPartials = @(Get-ChildItem -LiteralPath $runRoot -Force -File | Where-Object { $_.Name -like '.output.mp4.*.mp4' })
$events = Get-Content -LiteralPath $statusPath | ForEach-Object { $_ | ConvertFrom-Json }
if (-not ($events | Where-Object event -eq cancelled) -or
    ($events | Where-Object event -eq complete) -or
    (Test-Path -LiteralPath $cancelPath) -or
    $newPartials.Count -ne 0 -or
    (Test-Path -LiteralPath "$outputPath.partial.mp4") -or
    (Test-Path -LiteralPath "$outputPath.video-only.mp4") -or
    (Get-FileHash -LiteralPath $outputPath).Hash -ne $priorHash) {
    throw 'Cancellation cleanup/output preservation failed.'
}
$events | Where-Object event -eq cancelled | ConvertTo-Json
Write-Output $runRoot
