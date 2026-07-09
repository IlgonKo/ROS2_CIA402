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

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
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

    & $Python -B -m PyInstaller "packaging\axis_server.spec" --noconfirm --distpath "dist\pyinstaller" --workpath "build\pyinstaller"
    if ($LASTEXITCODE -ne 0) {
        throw "axis_server PyInstaller build failed"
    }

    & $Python -B -m PyInstaller "packaging\axis_control_panel.spec" --noconfirm --distpath "dist\pyinstaller" --workpath "build\pyinstaller"
    if ($LASTEXITCODE -ne 0) {
        throw "axis_control_panel PyInstaller build failed"
    }

    New-Item -ItemType Directory -Force $PackageRoot | Out-Null
    Copy-Item -Recurse -Force "dist\pyinstaller\axis_server\*" $PackageRoot
    Copy-Item -Recurse -Force "dist\pyinstaller\axis_control_panel\*" $PackageRoot

    New-Item -ItemType Directory -Force (Join-Path $PackageRoot "device\cmmt") | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $PackageRoot "Reference") | Out-Null
    New-Item -ItemType Directory -Force $ToolsRoot | Out-Null

    Copy-Item -Force ".env.example" (Join-Path $PackageRoot ".env.example")
    Copy-Item -Force "device\cmmt\.env.example" (Join-Path $PackageRoot "device\cmmt\.env.example")
    Copy-Item -Force "Reference\cmmt_error_catalog.json" (Join-Path $PackageRoot "Reference\cmmt_error_catalog.json")
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
            Copy-Item -Force ".env" (Join-Path $PackageRoot ".env")
        }
        if (Test-Path "device\cmmt\.env") {
            Copy-Item -Force "device\cmmt\.env" (Join-Path $PackageRoot "device\cmmt\.env")
        }
    }

    Write-Host "Built Windows package: $PackageRoot"
    if ($SkipLocalEnv) {
        Write-Host "Copy .env and device\cmmt\.env into that folder before running against real hardware."
    } else {
        Write-Host "Local .env files were copied into the package folder for this PC."
    }
}
finally {
    Pop-Location
}
