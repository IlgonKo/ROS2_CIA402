param(
    [string]$Python = "C:\Users\Festo\AppData\Local\Python\pythoncore-3.14-64\python.exe",
    [switch]$SkipInstall,
    [switch]$SkipLocalEnv,
    [switch]$SkipNpcapDownload
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$PackageRoot = Join-Path $ProjectRoot "dist\ROS2_CIA402"
$ToolsRoot = Join-Path $PackageRoot "Tools"
$PanelToolRoot = Join-Path $ToolsRoot "axis_control_panel"
$ManualRoot = Join-Path $PackageRoot "Manual"
$MotionServerIconPng = Join-Path $ProjectRoot "Reference\Motion Server.png"
$MotionServerIconIco = Join-Path $ProjectRoot "packaging\motion_server.ico"

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}

function Copy-WindowsConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $content = Get-Content -LiteralPath $Source -Raw
    $content = $content.Replace("device/cmmt/.env", "device/cmmt/config.txt")
    $content = $content.Replace("device/cpx_ap_i_ec/.env", "device/cpx_ap_i_ec/config.txt")
    $content = $content.Replace("device/virtual_servo_drive/.env", "device/virtual_servo_drive/config.txt")
    Set-Content -LiteralPath $Destination -Value $content -NoNewline
}

Push-Location $ProjectRoot
try {
    if (-not $SkipInstall) {
        & $Python -B -m pip show pyinstaller *> $null
        if ($LASTEXITCODE -ne 0) {
            & $Python -B -m pip install pyinstaller
            if ($LASTEXITCODE -ne 0) {
                throw "PyInstaller installation failed"
            }
        }
    }

    if (Test-Path $PackageRoot) {
        Remove-Item -Recurse -Force $PackageRoot
    }

    if (Test-Path $MotionServerIconPng) {
        $needsIconBuild = -not (Test-Path $MotionServerIconIco)
        if (-not $needsIconBuild) {
            $needsIconBuild = (
                (Get-Item $MotionServerIconPng).LastWriteTimeUtc -gt
                (Get-Item $MotionServerIconIco).LastWriteTimeUtc
            )
        }
        if ($needsIconBuild) {
            & $Python -B -c "from PIL import Image; from pathlib import Path; src=Path(r'$MotionServerIconPng'); dst=Path(r'$MotionServerIconIco'); img=Image.open(src).convert('RGBA'); img.save(dst, sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
            if ($LASTEXITCODE -ne 0) {
                throw "Motion Server icon conversion failed"
            }
        }
    } else {
        throw "Motion Server icon PNG not found: $MotionServerIconPng"
    }

    & $Python -B -m PyInstaller "packaging\motion_server.spec" --noconfirm --distpath "dist\pyinstaller" --workpath "build\pyinstaller"
    if ($LASTEXITCODE -ne 0) {
        throw "motion_server PyInstaller build failed"
    }

    & $Python -B -m PyInstaller "packaging\axis_control_panel.spec" --noconfirm --distpath "dist\pyinstaller" --workpath "build\pyinstaller"
    if ($LASTEXITCODE -ne 0) {
        throw "axis_control_panel PyInstaller build failed"
    }

    New-Item -ItemType Directory -Force $PackageRoot | Out-Null
    Copy-Item -Recurse -Force "dist\pyinstaller\motion_server\*" $PackageRoot

    New-Item -ItemType Directory -Force (Join-Path $PackageRoot "device\cmmt") | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $PackageRoot "device\cpx_ap_i_ec") | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $PackageRoot "device\virtual_servo_drive") | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $PackageRoot "Reference") | Out-Null
    New-Item -ItemType Directory -Force $ManualRoot | Out-Null
    New-Item -ItemType Directory -Force $ToolsRoot | Out-Null
    New-Item -ItemType Directory -Force $PanelToolRoot | Out-Null
    Copy-Item -Recurse -Force "dist\pyinstaller\axis_control_panel\*" $PanelToolRoot

    Copy-WindowsConfig ".env.example" (Join-Path $PackageRoot "config.example.txt")
    Copy-WindowsConfig "device\cmmt\.env.example" (Join-Path $PackageRoot "device\cmmt\config.example.txt")
    Copy-WindowsConfig "device\cpx_ap_i_ec\.env.example" (Join-Path $PackageRoot "device\cpx_ap_i_ec\config.example.txt")
    Copy-WindowsConfig "device\virtual_servo_drive\.env.example" (Join-Path $PackageRoot "device\virtual_servo_drive\config.example.txt")
    Copy-WindowsConfig "axis_control_panel\.env.example" (Join-Path $PanelToolRoot "config.example.txt")
    Copy-Item -Force "Reference\cmmt_error_catalog.json" (Join-Path $PackageRoot "Reference\cmmt_error_catalog.json")
    $manualFiles = Get-ChildItem -Path "Reference" -File -Filter "Motion_Server_User_Manual*"
    foreach ($manualFile in $manualFiles) {
        Copy-Item -Force $manualFile.FullName (Join-Path $ManualRoot $manualFile.Name)
    }
    Copy-Item -Force "packaging\WINDOWS_EXE.md" (Join-Path $PackageRoot "WINDOWS_EXE.md")
    Copy-Item -Force "scripts\windows\list_ethercat_nics.ps1" (Join-Path $ToolsRoot "list_ethercat_nics.ps1")

    if (-not $SkipNpcapDownload) {
        $NpcapUrl = "https://npcap.com/dist/npcap-1.88.exe"
        $NpcapInstaller = Join-Path $ToolsRoot "npcap-1.88.exe"
        Write-Host "Downloading Npcap installer: $NpcapUrl"
        Invoke-WebRequest -Uri $NpcapUrl -OutFile $NpcapInstaller
    }

    if (-not $SkipLocalEnv) {
        if (Test-Path ".env") {
            Copy-WindowsConfig ".env" (Join-Path $PackageRoot "config.txt")
        }
        if (Test-Path "device\cmmt\.env") {
            Copy-WindowsConfig "device\cmmt\.env" (Join-Path $PackageRoot "device\cmmt\config.txt")
        }
        if (Test-Path "device\cpx_ap_i_ec\.env") {
            Copy-WindowsConfig "device\cpx_ap_i_ec\.env" (Join-Path $PackageRoot "device\cpx_ap_i_ec\config.txt")
        }
        if (Test-Path "device\virtual_servo_drive\.env") {
            Copy-WindowsConfig "device\virtual_servo_drive\.env" (Join-Path $PackageRoot "device\virtual_servo_drive\config.txt")
        }
        if (Test-Path "axis_control_panel\.env") {
            Copy-WindowsConfig "axis_control_panel\.env" (Join-Path $PanelToolRoot "config.txt")
        }
    }

    Write-Host "Built Windows package: $PackageRoot"
    if ($SkipLocalEnv) {
        Write-Host "Create config.txt files from config.example.txt before running."
    } else {
        Write-Host "Local .env files were copied as Windows config.txt files for this PC."
    }
}
finally {
    Pop-Location
}
