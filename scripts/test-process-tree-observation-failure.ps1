[CmdletBinding()]
param([string]$SourcePath = 'out/media-smoke/fixture-720p30.mp4')
$ErrorActionPreference = 'Stop'
# Integration test: real packaged conversion, intentionally unavailable observer.
foreach ($treeTestScenario in @('error', 'missing')) {
    function Get-CimInstance {
        param($ClassName, $Property, $ErrorAction)
        if ($treeTestScenario -eq 'error') { throw 'Injected observation failure' }
        return @()
    }
    $outputLines = @(& (Join-Path $PSScriptRoot 'soak-v1.ps1') -SourcePath $SourcePath)
    $artifactPath = $outputLines[-1]
    $report = Get-Content -LiteralPath $artifactPath -Raw | ConvertFrom-Json
    $memory = $report.process_tree_memory
    if ($memory.sample_count -ne 0 -or $memory.coverage -ne 'unavailable' -or
        $null -ne $memory.sampled_max_private_bytes -or $null -ne $memory.last_private_bytes) {
        throw 'Unavailable memory was not represented as null.'
    }
    if ($treeTestScenario -eq 'error' -and $memory.observation_errors -lt 1) { throw 'Missing error count' }
    if ($treeTestScenario -eq 'missing' -and $memory.missing_root_snapshots -lt 1) { throw 'Missing absent-root count' }
    $totals = Import-Csv -LiteralPath $memory.totals_csv
    foreach ($row in $totals) {
        if ($row.state -eq 'observed' -or $row.private_bytes -ne '') { throw 'Unavailable CSV row claimed memory.' }
    }
    Write-Output "Observer $treeTestScenario integration passed: $artifactPath"
}
