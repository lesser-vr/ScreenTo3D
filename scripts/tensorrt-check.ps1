[CmdletBinding()]
param(
    [switch]$UpdateCurrentProcess
)

$ErrorActionPreference = 'Stop'

function Get-TensorRtBin {
    if ($env:TensorRT_PATH -and (Test-Path $env:TensorRT_PATH)) {
        return [Environment]::ExpandEnvironmentVariables($env:TensorRT_PATH)
    }

    $machine = Get-ItemProperty `
        'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' `
        -Name TensorRT_PATH -ErrorAction SilentlyContinue
    if ($machine.TensorRT_PATH) {
        $candidate = [Environment]::ExpandEnvironmentVariables($machine.TensorRT_PATH)
        if (Test-Path $candidate) { return $candidate }
    }

    $user = Get-ItemProperty 'HKCU:\Environment' -Name TensorRT_PATH `
        -ErrorAction SilentlyContinue
    if ($user.TensorRT_PATH) {
        $candidate = [Environment]::ExpandEnvironmentVariables($user.TensorRT_PATH)
        if (Test-Path $candidate) { return $candidate }
    }

    throw 'TensorRT_PATH does not resolve to an existing TensorRT bin directory.'
}

$bin = Get-TensorRtBin
$root = Split-Path $bin -Parent
$required = [ordered]@{
    trtexec = Join-Path $bin 'trtexec.exe'
    runtime_dll = Join-Path $bin 'nvinfer_11.dll'
    onnx_parser_dll = Join-Path $bin 'nvonnxparser_11.dll'
    header = Join-Path $root 'include\NvInfer.h'
    runtime_import_library = Join-Path $root 'lib\nvinfer_11.lib'
    onnx_parser_import_library = Join-Path $root 'lib\nvonnxparser_11.lib'
}

$missing = @($required.GetEnumerator() | Where-Object { -not (Test-Path $_.Value) })
if ($missing.Count -gt 0) {
    throw ('TensorRT installation is incomplete: ' +
        (($missing | ForEach-Object { $_.Key }) -join ', '))
}

if ($UpdateCurrentProcess) {
    $env:TensorRT_PATH = $bin
    if (($env:Path -split ';') -notcontains $bin) {
        $env:Path = "$bin;$env:Path"
    }
}

$versionLine = (& $required.trtexec --version 2>&1 |
    Select-String -Pattern 'TensorRT v[0-9]+' | Select-Object -First 1).Line
$version = if ($versionLine -match 'TensorRT v([0-9]+)') {
    $digits = $Matches[1]
    if ($digits.Length -ge 6) {
        '{0}.{1}.{2}' -f `
            [int]$digits.Substring(0, 2), `
            [int]$digits.Substring(2, 2), `
            [int]$digits.Substring(4, 2)
    } else {
        $digits
    }
} else {
    'unknown'
}

$builderResources = @(Get-ChildItem $bin -Filter 'nvinfer_builder_resource_*.dll' |
    Select-Object -ExpandProperty Name)

$result = [ordered]@{
    schema_version = 1
    available = $true
    version = $version
    root = $root
    bin = $bin
    current_process_updated = [bool]$UpdateCurrentProcess
    required_files = $required
    builder_resources = $builderResources
}

$result | ConvertTo-Json -Depth 4
