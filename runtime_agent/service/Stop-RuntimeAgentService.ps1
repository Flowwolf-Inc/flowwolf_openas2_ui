# Stop the OpenAS2 Runtime Agent Windows Service.
# Usage (elevated PowerShell): .\Stop-RuntimeAgentService.ps1

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service_common.ps1")
Assert-Administrator

$svc = Get-Service -Name $script:ServiceId -ErrorAction SilentlyContinue
if (-not $svc) {
    throw "Service '$($script:ServiceDisplayName)' is not installed."
}

if ($svc.Status -ne "Stopped") {
    Stop-Service -Name $script:ServiceId -Force
}
Start-Sleep -Seconds 1
Get-Service -Name $script:ServiceId | Format-List Name, DisplayName, Status, StartType
