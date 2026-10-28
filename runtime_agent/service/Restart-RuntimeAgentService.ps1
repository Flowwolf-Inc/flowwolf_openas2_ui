# Restart the OpenAS2 Runtime Agent Windows Service.
# Usage (elevated PowerShell): .\Restart-RuntimeAgentService.ps1

param([string]$DeployRoot = "C:\OpenAS2\agent")

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service_common.ps1")
Assert-Administrator

$svc = Get-Service -Name $script:ServiceId -ErrorAction SilentlyContinue
if (-not $svc) {
    throw "Service '$($script:ServiceDisplayName)' is not installed. Run Install-RuntimeAgentService.ps1 first."
}

Restart-Service -Name $script:ServiceId -Force
Start-Sleep -Seconds 1
Get-Service -Name $script:ServiceId | Format-List Name, DisplayName, Status, StartType
Write-Host "Logs: $(Join-Path $DeployRoot 'logs')"
