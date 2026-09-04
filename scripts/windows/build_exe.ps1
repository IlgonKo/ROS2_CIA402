param(
    [string]$Python = "C:\Users\Festo\AppData\Local\Python\pythoncore-3.14-64\python.exe",
    [switch]$SkipInstall,
    [switch]$SkipLocalEnv,
    [switch]$SkipNpcapDownload
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$PackageRoot = Join-Path $ProjectRoot "dist\Motion Server"
$ToolsRoot = Join-Path $PackageRoot "Tools"
$PanelToolRoot = Join-Path $ToolsRoot "axis_control_panel"
$IoPanelToolRoot = Join-Path $ToolsRoot "io_control_panel"
$ManualRoot = Join-Path $PackageRoot "Manual"
$IoddRoot = Join-Path $PackageRoot "device\io_link\iodd"
$ReferenceClientsRoot = Join-Path $PackageRoot "Reference Clients"
$NodeRedReferenceRoot = Join-Path $ReferenceClientsRoot "node_red"
$MotionServerIconPng = Join-Path $ProjectRoot "Reference\Motion Server.png"
$MotionServerIconIco = Join-Path $ProjectRoot "packaging\motion_server.ico"
$LegacyPyInstallerDistRoot = Join-Path $ProjectRoot "dist\pyinstaller"
$LegacyPyInstallerWorkRoot = Join-Path $ProjectRoot "build\pyinstaller"
$PyInstallerTempRoot = $null

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
    Set-Content -LiteralPath $Destination -Value $content -NoNewline
}

function Copy-NodeRedReferenceClient {
    $source = Join-Path $ProjectRoot "reference_clients\node_red\node-red-contrib-motion-server"
    $destination = Join-Path $NodeRedReferenceRoot "node-red-contrib-motion-server"

    if (-not (Test-Path $source)) {
        throw "Node-RED reference client not found: $source"
    }

    New-Item -ItemType Directory -Force $NodeRedReferenceRoot | Out-Null
    if (Test-Path $destination) {
        Remove-Item -Recurse -Force $destination
    }

    $exclude = @("node_modules", ".npm", ".cache")
    New-Item -ItemType Directory -Force $destination | Out-Null
    Get-ChildItem -LiteralPath $source -Force |
        Where-Object { $exclude -notcontains $_.Name } |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
        }
}

function New-PyInstallerTempRoot {
    $path = Join-Path ([System.IO.Path]::GetTempPath()) ("motion-server-pyinstaller-" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force $path | Out-Null
    return $path
}

function Remove-DirectoryIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
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
    Remove-DirectoryIfExists $LegacyPyInstallerDistRoot
    Remove-DirectoryIfExists $LegacyPyInstallerWorkRoot

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

    $PyInstallerTempRoot = New-PyInstallerTempRoot
    $PyInstallerDistRoot = Join-Path $PyInstallerTempRoot "dist"
    $PyInstallerWorkRoot = Join-Path $PyInstallerTempRoot "build"

    & $Python -B -m PyInstaller "packaging\motion_server.spec" --noconfirm --distpath $PyInstallerDistRoot --workpath $PyInstallerWorkRoot
    if ($LASTEXITCODE -ne 0) {
        throw "motion_server PyInstaller build failed"
    }

    & $Python -B -m PyInstaller "packaging\axis_control_panel.spec" --noconfirm --distpath $PyInstallerDistRoot --workpath $PyInstallerWorkRoot
    if ($LASTEXITCODE -ne 0) {
        throw "axis_control_panel PyInstaller build failed"
    }

    & $Python -B -m PyInstaller "packaging\io_control_panel.spec" --noconfirm --distpath $PyInstallerDistRoot --workpath $PyInstallerWorkRoot
    if ($LASTEXITCODE -ne 0) {
        throw "io_control_panel PyInstaller build failed"
    }

    New-Item -ItemType Directory -Force $PackageRoot | Out-Null
    Copy-Item -Recurse -Force (Join-Path $PyInstallerDistRoot "motion_server\*") $PackageRoot

    New-Item -ItemType Directory -Force (Join-Path $PackageRoot "device\cmmt") | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $PackageRoot "device\cpx_ap_i_ec") | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $PackageRoot "Reference") | Out-Null
    New-Item -ItemType Directory -Force $ManualRoot | Out-Null
    New-Item -ItemType Directory -Force $IoddRoot | Out-Null
    New-Item -ItemType Directory -Force $ToolsRoot | Out-Null
    New-Item -ItemType Directory -Force $PanelToolRoot | Out-Null
    New-Item -ItemType Directory -Force $IoPanelToolRoot | Out-Null
    Copy-Item -Recurse -Force (Join-Path $PyInstallerDistRoot "axis_control_panel\*") $PanelToolRoot
    Copy-Item -Recurse -Force (Join-Path $PyInstallerDistRoot "io_control_panel\*") $IoPanelToolRoot

    Copy-WindowsConfig ".env.example" (Join-Path $PackageRoot "config.example.txt")
    Copy-WindowsConfig "device\cmmt\.env.example" (Join-Path $PackageRoot "device\cmmt\config.example.txt")
    Copy-WindowsConfig "device\cpx_ap_i_ec\.env.example" (Join-Path $PackageRoot "device\cpx_ap_i_ec\config.example.txt")
    Copy-WindowsConfig "control_panel\axis_control_panel\.env.example" (Join-Path $PanelToolRoot "config.example.txt")
    Copy-WindowsConfig "control_panel\io_control_panel\.env.example" (Join-Path $IoPanelToolRoot "config.example.txt")
    Copy-Item -Force "Reference\cmmt_error_catalog.json" (Join-Path $PackageRoot "Reference\cmmt_error_catalog.json")
    Copy-NodeRedReferenceClient
    $manualFiles = Get-ChildItem -Path "docs" -File -Filter "Motion_Server_*_Manual*"
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
        if (Test-Path "control_panel\axis_control_panel\.env") {
            Copy-WindowsConfig "control_panel\axis_control_panel\.env" (Join-Path $PanelToolRoot "config.txt")
        }
        if (Test-Path "control_panel\io_control_panel\.env") {
            Copy-WindowsConfig "control_panel\io_control_panel\.env" (Join-Path $IoPanelToolRoot "config.txt")
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
    if ($null -ne $PyInstallerTempRoot) {
        Remove-DirectoryIfExists $PyInstallerTempRoot
    }
    Pop-Location
}
