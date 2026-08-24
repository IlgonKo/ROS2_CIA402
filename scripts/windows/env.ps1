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

    Push-Location $ProjectRoot
    try {
        $json = & $Python -m configuration --project-root $ProjectRoot --format json 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        $detail = ($json | Out-String).Trim()
        throw "Failed to load Motion Server configuration.`n$detail"
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

    $moduleRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
    Push-Location $moduleRoot
    try {
        $json = & $Python -m configuration --file $Path --format json 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        $detail = ($json | Out-String).Trim()
        throw "Failed to read configuration file: $Path`n$detail"
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
