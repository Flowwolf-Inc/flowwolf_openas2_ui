# Load env + run existing agent.py for the Windows Service (WinSW).
# Reuses the same env contract as start_agent.ps1. Does not rewrite agent.py.
# Token comes from C:\OpenAS2\agent\agent.env (never hardcoded).

param(
    [string]$DeployRoot = "",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"

if (-not $DeployRoot) {
    $DeployRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if (-not $EnvFile) {
    $EnvFile = Join-Path $DeployRoot "agent.env"
}

function Import-AgentEnvFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing env file: $Path. Run Install-RuntimeAgentService.ps1 -Token <token> first."
    }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        Set-Item -Path "Env:$name" -Value $value
    }
}

Import-AgentEnvFile -Path $EnvFile

if (-not $env:OPENAS2_AGENT_TOKEN) {
    throw "OPENAS2_AGENT_TOKEN is empty in $EnvFile"
}

$Root = if ($env:OPENAS2_ROOT) { $env:OPENAS2_ROOT } else { "C:\OpenAS2" }
$env:OPENAS2_ROOT = $Root
$env:OPENAS2_INSTANCES_ROOT = Join-Path $Root "instances"
$env:OPENAS2_RUNTIME_ROOT = Join-Path $Root "runtime"
if (-not $env:OPENAS2_AGENT_HOST) { $env:OPENAS2_AGENT_HOST = "0.0.0.0" }
if (-not $env:OPENAS2_AGENT_PORT) { $env:OPENAS2_AGENT_PORT = "9475" }

$AgentScript = Join-Path $DeployRoot "agent.py"
if (-not (Test-Path -LiteralPath $AgentScript)) {
    throw "agent.py not found at $AgentScript"
}

# Best-effort firewall (same idea as start_agent.ps1)
try {
    New-NetFirewallRule -DisplayName "OpenAS2 Runtime Agent" -Direction Inbound -Protocol TCP -LocalPort 9475 -Action Allow -ErrorAction SilentlyContinue | Out-Null
} catch {}

$python = $null
if ($env:OPENAS2_PYTHON -and (Test-Path -LiteralPath $env:OPENAS2_PYTHON)) {
    $python = $env:OPENAS2_PYTHON
} else {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $cmd) { throw "Python not found. Set OPENAS2_PYTHON in agent.env to the full path of python.exe" }
    $python = $cmd.Source
}

$logDir = Join-Path $DeployRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host ("[{0}] OpenAS2 Runtime Agent starting via service wrapper" -f (Get-Date -Format "o"))
Write-Host "DeployRoot=$DeployRoot Host=$($env:OPENAS2_AGENT_HOST) Port=$($env:OPENAS2_AGENT_PORT) Python=$python"
& $python $AgentScript
$exit = $LASTEXITCODE
Write-Host ("[{0}] agent.py exited with code {1}" -f (Get-Date -Format "o"), $exit)
exit $exit
