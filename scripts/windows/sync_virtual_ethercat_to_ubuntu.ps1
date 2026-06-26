param(
    [Parameter(Mandatory = $true)]
    [string]$User,

    [string]$HostName = "192.168.0.12",
    [int]$SshPort = 22,
    [string]$RemoteRoot = "/home/festo/Documents/ROS_CIA402",
    [switch]$UseSudoCleanup,
    [switch]$Watch,
    [int]$DebounceSeconds = 2
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ProjectName = Split-Path $ProjectRoot -Leaf

if ($ProjectName -ne "virtual_ethercat") {
    throw "Expected project root to be virtual_ethercat, got: $ProjectRoot"
}

if ($User -match "\\$") {
    throw "Invalid user '$User'. Use '-User festo', not '-User festo\'."
}

if ($User -match "@") {
    throw "Invalid user '$User'. Pass only the username, for example '-User festo'."
}

$RemoteLogin = "${User}@${HostName}"
$RemoteRootForShell = $RemoteRoot -replace '^~(?=/|$)', '$HOME'
$RemoteTarget = "${RemoteRootForShell}/${ProjectName}"
$RemoteArchive = "/tmp/${ProjectName}_sync.tar.gz"
$TempArchive = Join-Path $env:TEMP "${ProjectName}_sync.tar.gz"
$RemoteRemoveCommand = if ($UseSudoCleanup) { "sudo rm -rf" } else { "rm -rf" }

$ExcludePatterns = @(
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "install",
    "log",
    ".venv",
    "venv",
    ".git"
)

function Invoke-Sync {
    Write-Host ""
    Write-Host "Syncing ${ProjectRoot} -> ${RemoteLogin}:${RemoteTarget}"

    $tcpCheck = Test-NetConnection -ComputerName $HostName -Port $SshPort -InformationLevel Quiet
    if (-not $tcpCheck) {
        throw (
            "Cannot connect to ${HostName}:${SshPort}. " +
            "Check Ubuntu IP, network connection, firewall, and openssh-server."
        )
    }

    if (Test-Path $TempArchive) {
        Remove-Item -LiteralPath $TempArchive -Force
    }

    $tarArgs = @("-czf", $TempArchive)
    foreach ($pattern in $ExcludePatterns) {
        $tarArgs += "--exclude=$pattern"
    }
    $tarArgs += "-C"
    $tarArgs += (Split-Path $ProjectRoot -Parent)
    $tarArgs += $ProjectName

    & tar @tarArgs
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE"
    }

    & scp -P $SshPort $TempArchive "${RemoteLogin}:${RemoteArchive}"
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed with exit code $LASTEXITCODE"
    }

    $remoteCommand = @"
set -e
mkdir -p "$RemoteRootForShell"
case "$RemoteTarget" in
  */virtual_ethercat)
    if ! $RemoteRemoveCommand "$RemoteTarget"; then
      echo "Failed to remove $RemoteTarget." >&2
      echo "If Docker created root-owned files, run this once on Ubuntu:" >&2
      echo "  sudo chown -R ${User}:${User} $RemoteTarget" >&2
      echo "Then retry sync, or run sync with -UseSudoCleanup." >&2
      exit 1
    fi
    ;;
  *) echo "Refusing to remove unexpected path: $RemoteTarget" >&2; exit 1 ;;
esac
tar -xzf "$RemoteArchive" -C "$RemoteRootForShell"
rm -f "$RemoteArchive"
"@

    & ssh -p $SshPort "${RemoteLogin}" "bash -lc '$($remoteCommand -replace "'", "'\''")'"
    if ($LASTEXITCODE -ne 0) {
        throw "remote unpack failed with exit code $LASTEXITCODE"
    }

    Remove-Item -LiteralPath $TempArchive -Force
    Write-Host "Sync complete."
}

Invoke-Sync

if (-not $Watch) {
    exit 0
}

Write-Host ""
Write-Host "Watching for changes. Press Ctrl+C to stop."

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $ProjectRoot
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true

$lastChange = Get-Date
$pending = $false

$action = {
    $path = $Event.SourceEventArgs.FullPath
    if ($path -match "\\(__pycache__|\.git|\.venv|venv|build|install|log)(\\|$)") {
        return
    }

    $script:pending = $true
    $script:lastChange = Get-Date
}

$subscriptions = @(
    Register-ObjectEvent $watcher Changed -Action $action,
    Register-ObjectEvent $watcher Created -Action $action,
    Register-ObjectEvent $watcher Deleted -Action $action,
    Register-ObjectEvent $watcher Renamed -Action $action
)

try {
    while ($true) {
        Start-Sleep -Milliseconds 500
        if ($pending -and ((Get-Date) - $lastChange).TotalSeconds -ge $DebounceSeconds) {
            $pending = $false
            Invoke-Sync
        }
    }
}
finally {
    foreach ($subscription in $subscriptions) {
        Unregister-Event -SubscriptionId $subscription.Id
    }
    $watcher.Dispose()
}
