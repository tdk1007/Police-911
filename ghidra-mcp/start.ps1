# Start the shared headless GhidraMCP servers (idempotent).
#   .\ghidra-mcp\start.ps1            # all targets
#   .\ghidra-mcp\start.ps1 ps2        # one target
# Stop cleanly (saves the Ghidra project) with .\ghidra-mcp\stop.ps1.
param([string[]]$Target = @('arcade', 'ps2'))

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$Root = Split-Path $Here -Parent
. (Join-Path $Here 'targets.ps1')

$Py = Join-Path $Root 'tools\ghidramcp-venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { throw "Missing venv: $Py (see ghidra-mcp\README.md)" }
$env:GHIDRA_INSTALL_DIR = Join-Path $Root 'tools\ghidra_12.1.4_PUBLIC'
$Run = Join-Path $Here 'run'
New-Item -ItemType Directory -Force $Run | Out-Null

foreach ($name in $Target) {
    $t = $Targets[$name]
    if (-not $t) { throw "Unknown target '$name' (known: $($Targets.Keys -join ', '))" }
    if (Get-NetTCPConnection -LocalPort $t.Port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "$name already listening on $($t.Port)"
        continue
    }
    $argList = @("`"$Here\serve.py`"", $name, '--headless', '--transport', 'streamable-http',
        '--mcp-port', $t.Port, '--binary', "`"$Root\$($t.Binary)`"",
        '--project', "`"$Root\$($t.Project)`"", '--project-name', $t.ProjectName,
        '--save', '--ready-timeout', '3600') + $t.Extra
    Start-Process -FilePath $Py -ArgumentList $argList -WorkingDirectory $Run -WindowStyle Hidden `
        -RedirectStandardOutput "$Run\$name.out.log" -RedirectStandardError "$Run\$name.log" | Out-Null
    Write-Host "$name starting on http://127.0.0.1:$($t.Port)/mcp (log: ghidra-mcp\run\$name.log)"
}
