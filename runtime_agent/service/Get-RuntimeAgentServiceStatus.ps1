# Check OpenAS2 Runtime Agent Windows Service status.
# Usage: .\Get-RuntimeAgentServiceStatus.ps1
# Does not require elevation for a basic query.

param([string]$DeployRoot = "C:\OpenAS2\agent")

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service_common.ps1")

$paths = Get-ServiceDeployPaths -DeployRoot $DeployRoot
$svc = Get-Service -Name $script:ServiceId -ErrorAction SilentlyContinue

if (-not $svc) {
    Write-Host "Service '$($script:ServiceDisplayName)' is NOT installed."
    exit 1
}

$svc | Format-List Name, DisplayName, Status, StartType
Write-Host "DeployRoot : $($paths.DeployRoot)"
Write-Host "EnvFile    : $($paths.EnvFile) (exists=$(Test-Path -LiteralPath $paths.EnvFile))"
Write-Host "LogDir     : $($paths.LogDir)"
Write-Host "Exe        : $($paths.ExePath) (exists=$(Test-Path -LiteralPath $paths.ExePath))"

# Listening check (best-effort)
try {
    $listen = Get-NetTCPConnection -LocalPort 9475 -State Listen -ErrorAction SilentlyContinue
    if ($listen) {
        Write-Host "Port 9475  : LISTENING ($(($listen | Select-Object -ExpandProperty LocalAddress) -join ', '))"
    } else {
        Write-Host "Port 9475  : not listening"
    }
} catch {
    Write-Host "Port 9475  : (could not query — try: netstat -ano | findstr :9475)"
}
