# Cleanly stop headless GhidraMCP servers; each saves its Ghidra project first.
#   .\ghidra-mcp\stop.ps1            # all targets
#   .\ghidra-mcp\stop.ps1 arcade     # one target (e.g. before opening it in the Ghidra GUI)
param([string[]]$Target = @('arcade', 'ps2'), [int]$TimeoutSec = 120)

$Here = $PSScriptRoot
. (Join-Path $Here 'targets.ps1')
$Run = Join-Path $Here 'run'

foreach ($name in $Target) {
    $pidFile = Join-Path $Run "$name.pid"
    if (-not (Test-Path $pidFile)) { Write-Host "$name not running"; continue }
    $procId = [int](Get-Content $pidFile)
    New-Item -ItemType File -Force (Join-Path $Run "$name.stop") | Out-Null
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p -and -not $p.WaitForExit($TimeoutSec * 1000)) {
        Write-Warning "$name (pid $procId) did not exit in $TimeoutSec s; NOT killed so it can finish saving"
        continue
    }
    Remove-Item -ErrorAction SilentlyContinue $pidFile, (Join-Path $Run "$name.stop")
    Write-Host "$name stopped (project saved)"
}
