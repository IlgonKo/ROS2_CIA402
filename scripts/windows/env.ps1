function Read-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $values = [ordered]@{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $values
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $parts = $trimmed.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        $values[$key] = $value
    }

    return $values
}

function Import-AxisServerEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $baseEnvPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path -LiteralPath $baseEnvPath)) {
        throw "Missing $baseEnvPath. Create it from .env.example first."
    }

    $merged = [ordered]@{}
    foreach ($entry in (Read-DotEnvFile -Path $baseEnvPath).GetEnumerator()) {
        $merged[$entry.Key] = $entry.Value
    }

    $deviceConfigRoot = $merged["PYSOEM_DEVICE_CONFIG_ROOT"]
    if ([string]::IsNullOrWhiteSpace($deviceConfigRoot)) {
        $deviceConfigRoot = "device"
    }
    if (-not [System.IO.Path]::IsPathRooted($deviceConfigRoot)) {
        $deviceConfigRoot = Join-Path $ProjectRoot $deviceConfigRoot
    }
    $bus = $merged["PYSOEM_BUS"]
    if ([string]::IsNullOrWhiteSpace($bus)) {
        $bus = "cmmt"
    }
    $loadedProfiles = @{}
    foreach ($busEntry in @($bus.Split(","))) {
        $entry = $busEntry.Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($entry)) {
            continue
        }
        $profile = $entry
        if ($entry.Contains(":")) {
            $profile = $entry.Split(":", 2)[1].Trim()
        }
        if ($loadedProfiles.ContainsKey($profile)) {
            continue
        }
        $loadedProfiles[$profile] = $true
        $deviceEnvFile = Join-Path (Join-Path $deviceConfigRoot $profile) ".env"
        if (Test-Path -LiteralPath $deviceEnvFile) {
            foreach ($entry in (Read-DotEnvFile -Path $deviceEnvFile).GetEnumerator()) {
                $merged[$entry.Key] = $entry.Value
            }
        } else {
            Write-Warning "Device env file not found: $deviceEnvFile"
        }
    }

    $backend = $merged["MOTION_SERVER_BACKEND"]
    if ([string]::IsNullOrWhiteSpace($backend)) {
        $backend = $merged["AXIS_SERVER_BACKEND"]
    }
    if ($backend -eq "mock") {
        $virtualEnvFile = $merged["VIRTUAL_SERVO_DRIVE_ENV_FILE"]
        if ([string]::IsNullOrWhiteSpace($virtualEnvFile)) {
            $virtualEnvFile = "device/virtual_servo_drive/.env"
        }
        if (-not [System.IO.Path]::IsPathRooted($virtualEnvFile)) {
            $virtualEnvFile = Join-Path $ProjectRoot $virtualEnvFile
        }
        if (Test-Path -LiteralPath $virtualEnvFile) {
            foreach ($entry in (Read-DotEnvFile -Path $virtualEnvFile).GetEnumerator()) {
                $merged[$entry.Key] = $entry.Value
            }
        } else {
            Write-Warning "Virtual servo drive env file not found: $virtualEnvFile"
        }
    }

    foreach ($entry in $merged.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
    }

    return $merged
}

function Get-AxisServerEnvValue {
    param(
        [hashtable]$EnvValues,
        [string]$Name,
        [string]$Default = ""
    )

    if ($EnvValues.Contains($Name) -and -not [string]::IsNullOrWhiteSpace($EnvValues[$Name])) {
        return [string]$EnvValues[$Name]
    }
    return $Default
}
