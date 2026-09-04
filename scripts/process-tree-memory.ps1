function Select-WorkerProcessTree {
    param([object[]]$Rows, [int]$RootId, [datetime]$RootStartedUtc)
    $root = $Rows | Where-Object { [int]$_.ProcessId -eq $RootId } | Select-Object -First 1
    if (-not $root -or -not $root.CreationDate -or
        [Math]::Abs(($root.CreationDate.ToUniversalTime() - $RootStartedUtc.ToUniversalTime()).Ticks) -gt 10) {
        return
    }
    $selected = @{}
    $selected[$RootId] = $root
    do {
        $added = $false
        foreach ($row in $Rows) {
            $childId = [int]$row.ProcessId
            $parentId = [int]$row.ParentProcessId
            if ($selected.ContainsKey($childId) -or -not $selected.ContainsKey($parentId)) { continue }
            $parent = $selected[$parentId]
            if (-not $row.CreationDate -or $row.CreationDate -lt $parent.CreationDate) { continue }
            $selected[$childId] = $row
            $added = $true
        }
    } while ($added)
    $selected.Values | Sort-Object ProcessId
}
