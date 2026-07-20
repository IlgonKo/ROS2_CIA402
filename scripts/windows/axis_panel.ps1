param(
    [string]$HostName = "",
    [int]$Port = 0,
    [string]$Python = "C:\Users\Festo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
)

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
. (Join-Path $PSScriptRoot "env.ps1")
$AxisEnv = Import-AxisServerEnv -ProjectRoot $ProjectRoot

if ([string]::IsNullOrWhiteSpace($HostName)) {
    $HostName = Get-AxisServerEnvValue -EnvValues $AxisEnv -Name "AXIS_SERVER_HOST" -Default "127.0.0.1"
}
if ($Port -le 0) {
    $Port = [int](Get-AxisServerEnvValue -EnvValues $AxisEnv -Name "AXIS_SERVER_PORT" -Default "15000")
}
$env:AXIS_SERVER_HOST = $HostName
$env:AXIS_SERVER_PORT = [string]$Port
$env:PYTHONPATH = "$ProjectRoot;$env:PYTHONPATH"
$Bus = Get-AxisServerEnvValue -EnvValues $AxisEnv -Name "PYSOEM_BUS" -Default "cmmt"

Write-Host "Starting Axis Control Panel"
Write-Host "Host=$HostName"
Write-Host "Port=$Port"
Write-Host "Bus=$Bus"
Write-Host "PYTHONPATH=$env:PYTHONPATH"

& $Python -B (Join-Path $ProjectRoot "motion_server\control_panel.py")
