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

    $deviceEnvFile = $merged["PYSOEM_DEVICE_ENV_FILE"]
    if ([string]::IsNullOrWhiteSpace($deviceEnvFile)) {
        $device = $merged["PYSOEM_DEVICE"]
        if ($device -eq "cmmt") {
            $deviceEnvFile = "device/cmmt/.env"
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($deviceEnvFile)) {
        if (-not [System.IO.Path]::IsPathRooted($deviceEnvFile)) {
            $deviceEnvFile = Join-Path $ProjectRoot $deviceEnvFile
        }
        if (Test-Path -LiteralPath $deviceEnvFile) {
            foreach ($entry in (Read-DotEnvFile -Path $deviceEnvFile).GetEnumerator()) {
                $merged[$entry.Key] = $entry.Value
            }
        } else {
            Write-Warning "Device env file not found: $deviceEnvFile"
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
