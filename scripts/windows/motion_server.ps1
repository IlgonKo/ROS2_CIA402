param(
    [string]$Interface = "",
    [int]$Port = 0,
    [string]$Backend = "",
    [string]$ServerMode = "",
    [string]$Bus = "",
    [string]$Python = "C:\Users\Festo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
)

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
. (Join-Path $PSScriptRoot "env.ps1")
$AxisEnv = Import-AxisServerEnv -ProjectRoot $ProjectRoot -Python $Python

if ([string]::IsNullOrWhiteSpace($Interface)) {
    $Interface = Get-AxisServerEnvValue -EnvValues $AxisEnv -Name "PYSOEM_INTERFACE" -Default "\Device\NPF_{906A65C9-C606-4B1F-8384-2625829A4D18}"
}
if ($Port -le 0) {
    $Port = [int](Get-AxisServerEnvValue -EnvValues $AxisEnv -Name "MOTION_SERVER_PORT" -Default "15000")
}
if ([string]::IsNullOrWhiteSpace($Backend)) {
    $Backend = Get-AxisServerEnvValue -EnvValues $AxisEnv -Name "MOTION_SERVER_BACKEND" -Default "pysoem"
}
if ([string]::IsNullOrWhiteSpace($ServerMode)) {
    $ServerMode = Get-AxisServerEnvValue -EnvValues $AxisEnv -Name "MOTION_SERVER_MODE" -Default "basic"
}
if ([string]::IsNullOrWhiteSpace($Bus)) {
    $Bus = Get-AxisServerEnvValue -EnvValues $AxisEnv -Name "MOTION_SERVER_BUS" -Default "cmmt_as"
}

$env:PYTHONPATH = "$ProjectRoot;$env:PYTHONPATH"

Write-Host "Starting Motion Server"
Write-Host "Backend=$Backend"
Write-Host "ServerMode=$ServerMode"
Write-Host "Interface=$Interface"
Write-Host "Bus=$Bus"
Write-Host "Port=$Port"
Write-Host "PYTHONPATH=$env:PYTHONPATH"

$Arguments = @(
    "-B",
    (Join-Path $ProjectRoot "motion_server\server.py"),
    $Interface,
    "--backend", $Backend,
    "--server-mode", $ServerMode,
    "--bus", $Bus,
    "--port", $Port
)

& $Python @Arguments
