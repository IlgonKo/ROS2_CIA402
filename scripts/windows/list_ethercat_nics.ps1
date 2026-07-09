$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageRoot = Resolve-Path (Join-Path $ScriptDir "..")
$AxisServer = Join-Path $PackageRoot "axis_server.exe"

if (-not (Test-Path $AxisServer)) {
    throw "axis_server.exe not found: $AxisServer"
}

Write-Host "EtherCAT/Npcap adapters:"
Write-Host ""
& $AxisServer --list-adapters

Write-Host "Use the full name value in .env as PYSOEM_INTERFACE."
Write-Host "Example:"
Write-Host 'PYSOEM_INTERFACE=\Device\NPF_{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}'
