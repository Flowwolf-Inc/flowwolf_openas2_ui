# Uninstall the OpenAS2 Runtime Agent Windows Service.
# Leaves C:\OpenAS2\agent files and agent.env in place unless -RemoveDeployFiles.
# Does not touch OpenAS2 instances or Downloads\OpenAS20|A|B.
#
# Usage (elevated PowerShell):
#   .\Uninstall-RuntimeAgentService.ps1
#   .\Uninstall-RuntimeAgentService.ps1 -RemoveDeployFiles

param(
    [string]$DeployRoot = "C:\OpenAS2\agent",
    [switch]$RemoveDeployFiles,
    [switch]$RemoveEnvFile
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service_common.ps1")
Assert-Administrator

$paths = Get-ServiceDeployPaths -DeployRoot $DeployRoot
$svc = Get-Service -Name $script:ServiceId -ErrorAction SilentlyContinue

if ($svc) {
    if ($svc.Status -ne "Stopped") {
        Write-Host "Stopping service..."
        Stop-Service -Name $script:ServiceId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    if (Test-Path -LiteralPath $paths.ExePath) {
        Write-Host "Uninstalling via WinSW..."
        & $paths.ExePath uninstall
    } else {
        Write-Host "WinSW exe missing; removing service with sc.exe..."
        sc.exe delete $script:ServiceId | Out-Null
    }
    Start-Sleep -Seconds 2
} else {
    Write-Host "Service not installed (nothing to uninstall)."
}

if ($RemoveEnvFile -and (Test-Path -LiteralPath $paths.EnvFile)) {
    Remove-Item -LiteralPath $paths.EnvFile -Force
    Write-Host "Removed $($paths.EnvFile)"
}

if ($RemoveDeployFiles -and (Test-Path -LiteralPath $DeployRoot)) {
    Write-Host "Removing deploy tree $DeployRoot (instances/runtime untouched)..."
    Remove-Item -LiteralPath $DeployRoot -Recurse -Force
}

$left = Get-Service -Name $script:ServiceId -ErrorAction SilentlyContinue
if ($left) {
    Write-Warning "Service still present: $($left.Status). A reboot may be required after sc delete."
} else {
    Write-Host "Uninstall complete. Manual fallback still works: ..\start_agent.ps1 -Token <token>"
}
