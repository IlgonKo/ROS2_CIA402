function Import-AxisServerEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [string]$Python = "python"
    )

    $baseEnvPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path -LiteralPath $baseEnvPath)) {
        throw "Missing $baseEnvPath. Create it from .env.example first."
    }

    $json = & $Python -m configuration --project-root $ProjectRoot --format json
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to load Motion Server configuration."
    }

    $parsed = $json | ConvertFrom-Json
    $merged = [ordered]@{}
    foreach ($property in $parsed.PSObject.Properties) {
        $merged[$property.Name] = [string]$property.Value
    }

    foreach ($entry in $merged.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
    }

    return $merged
}

function Read-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [string]$Python = "python"
    )

    $json = & $Python -m configuration --file $Path --format json
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read configuration file: $Path"
    }
    $parsed = $json | ConvertFrom-Json
    $values = [ordered]@{}
    foreach ($property in $parsed.PSObject.Properties) {
        $values[$property.Name] = [string]$property.Value
    }
    return $values
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
