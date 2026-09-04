$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'process-tree-memory.ps1')
$start = [datetime]'2026-09-04T00:00:00Z'
function Row($id, $parent, $offset) {
    [pscustomobject]@{ ProcessId=$id; ParentProcessId=$parent; CreationDate=$start.AddSeconds($offset) }
}
$rows = @((Row 3 2 2), (Row 1 0 0), (Row 2 1 1), (Row 4 0 1), (Row 5 2 -1))
$tree = @(Select-WorkerProcessTree -Rows $rows -RootId 1 -RootStartedUtc $start)
if (($tree.ProcessId -join ',') -ne '1,2,3') { throw 'Descendant/unrelated/older-child selection failed' }
if (@(Select-WorkerProcessTree -Rows $rows -RootId 9 -RootStartedUtc $start).Count -ne 0) { throw 'Missing root failed' }
if (@(Select-WorkerProcessTree -Rows $rows -RootId 1 -RootStartedUtc $start.AddSeconds(-10)).Count -ne 0) { throw 'PID reuse failed' }
if (@(Select-WorkerProcessTree -Rows $rows -RootId 1 -RootStartedUtc $start.AddMilliseconds(-1)).Count -ne 0) { throw 'Rapid PID reuse failed' }
if (@(Select-WorkerProcessTree -Rows $rows -RootId 1 -RootStartedUtc $start.AddTicks(9)).Count -ne 3) { throw 'CIM timestamp precision failed' }
$orphan = @((Row 1 0 0), (Row 3 2 2))
if (@(Select-WorkerProcessTree -Rows $orphan -RootId 1 -RootStartedUtc $start).Count -ne 1) { throw 'Missing parent failed' }
$missingTime = Row 1 0 0
$missingTime.CreationDate = $null
if (@(Select-WorkerProcessTree -Rows @($missingTime) -RootId 1 -RootStartedUtc $start).Count -ne 0) { throw 'Missing creation time failed' }
Write-Output 'Process-tree selection tests passed (7 cases).'
