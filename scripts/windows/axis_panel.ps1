param(
    [string]$HostName = "",
    [int]$Port = 0,
    [string]$Python = "C:\Users\Festo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
)

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
. (Join-Path $PSScriptRoot "env.ps1")
$PanelConfigRoot = Join-Path $ProjectRoot "control_panel\axis_control_panel"
$PanelEnvPath = Join-Path $PanelConfigRoot ".env"
$PanelEnv = Read-DotEnvFile -Path $PanelEnvPath -Python $Python

if ([string]::IsNullOrWhiteSpace($HostName)) {
    $HostName = Get-AxisServerEnvValue -EnvValues $PanelEnv -Name "MOTION_SERVER_HOST" -Default "127.0.0.1"
}
if ($Port -le 0) {
    $Port = [int](Get-AxisServerEnvValue -EnvValues $PanelEnv -Name "MOTION_SERVER_PORT" -Default "15000")
}
$env:MOTION_SERVER_HOST = $HostName
$env:MOTION_SERVER_PORT = [string]$Port
$env:AXIS_CONTROL_PANEL_CONFIG_ROOT = $PanelConfigRoot
$ResolvedProjectRoot = Set-AxisServerPythonPath -ProjectRoot $ProjectRoot

Write-Host "Starting Axis Control Panel"
Write-Host "Host=$HostName"
Write-Host "Port=$Port"
Write-Host "Config=$PanelEnvPath"
Write-Host "Project root: $ResolvedProjectRoot"

Push-Location $ProjectRoot
try {
    & $Python -B -m control_panel.axis_control_panel.control_panel
}
finally {
    Pop-Location
}
