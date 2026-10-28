# One-time install of the OpenAS2 Runtime Agent as a Windows Service (WinSW).
# Does NOT start OpenAS2 Java instances as services.
# Does NOT modify OpenAS20 / OpenAS2A / OpenAS2B or Phase 1 provisioning.
#
# Usage (elevated PowerShell):
#   cd <repo>\runtime_agent\service
#   .\Install-RuntimeAgentService.ps1 -Token "your-token"
#   .\Install-RuntimeAgentService.ps1 -Token "your-token" -Start

param(
    [string]$Token = $env:OPENAS2_AGENT_TOKEN,
    [string]$SourceRoot = "",
    [string]$DeployRoot = "C:\OpenAS2\agent",
    [string]$OpenAs2Root = "C:\OpenAS2",
    [string]$PythonExe = "",
    [string]$WinSWExe = "",
    [switch]$Start,
    [switch]$ForceReinstall
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service_common.ps1")

Assert-Administrator

if (-not $Token) {
    throw "Provide -Token or set OPENAS2_AGENT_TOKEN (token is written to $DeployRoot\agent.env, not into the repo)."
}

if (-not $SourceRoot) {
    $SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$paths = Get-ServiceDeployPaths -DeployRoot $DeployRoot
$PythonExe = Resolve-PythonExe -Preferred $PythonExe

Write-Host "SourceRoot  = $SourceRoot"
Write-Host "DeployRoot  = $DeployRoot"
Write-Host "OpenAs2Root = $OpenAs2Root"
Write-Host "PythonExe   = $PythonExe"
Write-Host "Service     = $($script:ServiceDisplayName) (id=$($script:ServiceId))"

# Deploy agent files (reuse existing agent.py / start_agent.ps1)
New-Item -ItemType Directory -Force -Path $paths.DeployRoot, $paths.ServiceDir, $paths.LogDir | Out-Null

$copyMap = @{
    (Join-Path $SourceRoot "agent.py") = $paths.AgentScript
    (Join-Path $SourceRoot "start_agent.ps1") = $paths.StartAgentPs1
    (Join-Path $SourceRoot "service\run_agent_for_service.ps1") = $paths.RunnerPs1
    (Join-Path $SourceRoot "service\_service_common.ps1") = (Join-Path $paths.ServiceDir "_service_common.ps1")
    (Join-Path $SourceRoot "service\OpenAS2RuntimeAgent.xml") = $paths.XmlPath
    (Join-Path $SourceRoot "service\Install-RuntimeAgentService.ps1") = (Join-Path $paths.ServiceDir "Install-RuntimeAgentService.ps1")
    (Join-Path $SourceRoot "service\Start-RuntimeAgentService.ps1") = (Join-Path $paths.ServiceDir "Start-RuntimeAgentService.ps1")
    (Join-Path $SourceRoot "service\Stop-RuntimeAgentService.ps1") = (Join-Path $paths.ServiceDir "Stop-RuntimeAgentService.ps1")
    (Join-Path $SourceRoot "service\Restart-RuntimeAgentService.ps1") = (Join-Path $paths.ServiceDir "Restart-RuntimeAgentService.ps1")
    (Join-Path $SourceRoot "service\Get-RuntimeAgentServiceStatus.ps1") = (Join-Path $paths.ServiceDir "Get-RuntimeAgentServiceStatus.ps1")
    (Join-Path $SourceRoot "service\Uninstall-RuntimeAgentService.ps1") = (Join-Path $paths.ServiceDir "Uninstall-RuntimeAgentService.ps1")
}

foreach ($src in $copyMap.Keys) {
    if (-not (Test-Path -LiteralPath $src)) {
        throw "Missing source file: $src"
    }
    Copy-Item -LiteralPath $src -Destination $copyMap[$src] -Force
}

Write-AgentEnvFile -Path $paths.EnvFile -Token $Token -OpenAs2Root $OpenAs2Root -PythonExe $PythonExe
Write-Host "Wrote token/env to $($paths.EnvFile) (not in git)."

# WinSW binary (same basename as XML)
if ($WinSWExe) {
    if (-not (Test-Path -LiteralPath $WinSWExe)) {
        throw "WinSWExe not found: $WinSWExe"
    }
    Copy-Item -LiteralPath $WinSWExe -Destination $paths.ExePath -Force
} else {
    Ensure-WinSW -ExePath $paths.ExePath
}

# Firewall (WSL / remote Manager reachability)
try {
    New-NetFirewallRule -DisplayName "OpenAS2 Runtime Agent" -Direction Inbound -Protocol TCP -LocalPort 9475 -Action Allow -ErrorAction SilentlyContinue | Out-Null
} catch {}

$existing = Get-Service -Name $script:ServiceId -ErrorAction SilentlyContinue
if ($existing -and $ForceReinstall) {
    Write-Host "ForceReinstall: stopping and uninstalling existing service..."
    if ($existing.Status -eq "Running") {
        Stop-Service -Name $script:ServiceId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    & $paths.ExePath uninstall
    Start-Sleep -Seconds 2
    $existing = Get-Service -Name $script:ServiceId -ErrorAction SilentlyContinue
}

if (-not $existing) {
    Write-Host "Installing Windows Service via WinSW..."
    & $paths.ExePath install
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        throw "WinSW install failed with exit code $LASTEXITCODE"
    }
} else {
    Write-Host "Service already installed (use -ForceReinstall to recreate). Refreshing files/env only."
}

# SCM failure actions (in addition to WinSW <onfailure>)
sc.exe failure $script:ServiceId reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
sc.exe config $script:ServiceId start= auto | Out-Null

if ($Start) {
    Start-Service -Name $script:ServiceId
    Write-Host "Service started."
} else {
    Write-Host "Install complete. Start with: .\Start-RuntimeAgentService.ps1"
}

Get-Service -Name $script:ServiceId | Format-List Name, DisplayName, Status, StartType
