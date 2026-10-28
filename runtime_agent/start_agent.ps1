# Start OpenAS2 Runtime Agent (Phase 2) — manual / fallback launcher.
# Prefer the Windows Service when installed:
#   .\service\Install-RuntimeAgentService.ps1 -Token <token>
#   .\service\Start-RuntimeAgentService.ps1
# This script remains the supported interactive fallback.
# Does not install Windows Services by itself. Does not touch Downloads\OpenAS20|A|B.

param(
    [string]$Token = $env:OPENAS2_AGENT_TOKEN,
    [string]$Root = "C:\OpenAS2",
    [string]$AgentScript = ""
)

$ErrorActionPreference = "Stop"

if (-not $Token) {
    Write-Error "Set -Token or OPENAS2_AGENT_TOKEN"
}

if (-not $AgentScript) {
    $AgentScript = Join-Path $PSScriptRoot "agent.py"
}

$env:OPENAS2_AGENT_TOKEN = $Token
$env:OPENAS2_ROOT = $Root
$env:OPENAS2_INSTANCES_ROOT = Join-Path $Root "instances"
$env:OPENAS2_RUNTIME_ROOT = Join-Path $Root "runtime"
$env:OPENAS2_AGENT_HOST = "0.0.0.0"
$env:OPENAS2_AGENT_PORT = "9475"

# Allow WSL → Windows (Hyper-V) access to the agent
try {
    New-NetFirewallRule -DisplayName "OpenAS2 Runtime Agent" -Direction Inbound -Protocol TCP -LocalPort 9475 -Action Allow -ErrorAction SilentlyContinue | Out-Null
} catch {}

$lib = Join-Path $env:OPENAS2_RUNTIME_ROOT "lib"
if (-not (Test-Path (Join-Path $lib "openas2-server-4.8.3.jar"))) {
    Write-Warning "Shared runtime lib missing. Copy OpenAS20\lib into $lib before Start will succeed."
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Error "Python not found on PATH"
}

Write-Host "Starting agent: $AgentScript"
& $python.Source $AgentScript
