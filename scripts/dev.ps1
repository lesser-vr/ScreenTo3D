[CmdletBinding()]
param(
    [ValidateSet('configure', 'build', 'test', 'check', 'capability')]
    [string]$Action = 'check',
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$preset = if ($Configuration -eq 'Release') {
    'windows-msvc-release'
} else {
    'windows-msvc-debug'
}

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) {
    throw 'Visual Studio Installer vswhere.exe was not found.'
}

$vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) {
    throw 'A Visual Studio installation with C++ tools was not found.'
}

$devShell = Join-Path $vsPath 'Common7\Tools\Launch-VsDevShell.ps1'
$cmake = Join-Path $vsPath 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
$ninjaDirectory = Join-Path $vsPath 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja'

if (-not (Test-Path $devShell)) { throw "Developer shell not found: $devShell" }
if (-not (Test-Path $cmake)) { throw "Bundled CMake not found: $cmake" }

& $devShell -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$env:Path = "$ninjaDirectory;$env:Path"

function Invoke-Configure {
    & $cmake --preset $preset -S $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'CMake configure failed.' }
}

function Invoke-Build {
    Invoke-Configure
    & $cmake --build --preset $preset
    if ($LASTEXITCODE -ne 0) { throw 'CMake build failed.' }
}

switch ($Action) {
    'configure' { Invoke-Configure }
    'build' { Invoke-Build }
    'test' {
        Invoke-Build
        & $cmake --build (Join-Path $repoRoot "out\build\$preset") --target test
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    }
    'check' {
        Invoke-Build
        & $cmake --build (Join-Path $repoRoot "out\build\$preset") --target test
        if ($LASTEXITCODE -ne 0) { throw 'Checks failed.' }
    }
    'capability' {
        Invoke-Build
        $executable = Join-Path $repoRoot "out\build\$preset\depthsbs.exe"
        & $executable capability
        if ($LASTEXITCODE -ne 0) { throw 'Capability probe failed.' }
    }
}
