param(
    [string]$Interface = "\Device\NPF_{906A65C9-C606-4B1F-8384-2625829A4D18}",
    [int]$AxisCount = 1,
    [int]$Port = 15000,
    [string]$Python = "C:\Users\Festo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
)

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$env:PYTHONPATH = "$ProjectRoot;$env:PYTHONPATH"

Write-Host "Starting PySOEM axis server"
Write-Host "Interface=$Interface"
Write-Host "AxisCount=$AxisCount"
Write-Host "Port=$Port"
Write-Host "PYTHONPATH=$env:PYTHONPATH"

& $Python (Join-Path $ProjectRoot "axis_server\server.py") $Interface --port $Port --axis-count $AxisCount
