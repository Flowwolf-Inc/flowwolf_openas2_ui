# OpenAS2 Runtime Agent (Phase 2)

Windows HTTP control plane that starts/stops Manager-provisioned OpenAS2 Java processes.

**Phase 2A:** the Runtime Agent itself can run as a Windows Service (`OpenAS2 Runtime Agent`). OpenAS2 Java instances still use the Phase 2 PID/process model (not Windows Services yet).

## Layout

```
C:\OpenAS2\
  runtime\lib\          shared OpenAS2 4.8.3 jars (copy from a distro; do not alter Downloads installs)
  instances\<slug>\     per-instance config/data/logs/keystore + manager_manifest.json
  agent\                deploy copy of this agent (created by the service installer)
    agent.py
    start_agent.ps1     manual fallback
    agent.env           SECRET — bearer token (not in git)
    logs\               WinSW + agent stdout/stderr service logs
    service\            WinSW exe/xml + manage scripts
```

## Token configuration (do not hardcode)

| Location | Purpose |
| --- | --- |
| `C:\OpenAS2\agent\agent.env` | **Live token** for the Windows Service / service runner (`OPENAS2_AGENT_TOKEN=...`). Created by the installer. **Never commit.** |
| `runtime_agent/agent.env.example` | Template only (safe to commit). |
| Frappe `site_config.json` | `openas2_runtime_agent_token` + `openas2_runtime_agent_url` (Manager side). |
| Manual fallback | `-Token` / `$env:OPENAS2_AGENT_TOKEN` for `start_agent.ps1`. |

The checked-in WinSW XML does **not** contain the token. `run_agent_for_service.ps1` loads `agent.env` at process start.

## Quick start (manual fallback)

1. Copy jars (read-only source):

```powershell
New-Item -ItemType Directory -Force C:\OpenAS2\runtime\lib | Out-Null
Copy-Item -Recurse -Force "C:\Users\laksh\Downloads\OpenAS20\lib\*" C:\OpenAS2\runtime\lib\
```

2. Start interactively (still supported):

```powershell
cd <path-to>\openas2_manager\runtime_agent
.\start_agent.ps1 -Token "change-me-to-a-long-random-token"
```

Or:

```powershell
$env:OPENAS2_AGENT_TOKEN = "change-me-to-a-long-random-token"
$env:OPENAS2_ROOT = "C:\OpenAS2"
$env:OPENAS2_AGENT_HOST = "0.0.0.0"
$env:OPENAS2_AGENT_PORT = "9475"
python .\agent.py
```

3. Configure Frappe `site_config.json`:

```json
{
  "openas2_runtime_agent_url": "http://127.0.0.1:9475",
  "openas2_runtime_agent_token": "change-me-to-a-long-random-token"
}
```

From WSL, use the Windows host IP when mirrored networking is not enabled (`cat /etc/resolv.conf`).

## Windows Service (Phase 2A) — recommended

Mechanism: **[WinSW](https://github.com/winsw/winsw)** wraps the existing `python agent.py` (via `run_agent_for_service.ps1`). No extra Python packages. Service name: **OpenAS2 Runtime Agent**. Start type: Automatic. Restart on failure via WinSW `<onfailure>` and `sc failure`.

### One-time install (elevated PowerShell)

From the repo (or any checkout of `runtime_agent`):

```powershell
cd \\wsl$\Ubuntu\home\laksh\openas2_bench\apps\openas2_manager\runtime_agent\service
# Or after copying runtime_agent to a Windows path:
# cd C:\path\to\openas2_manager\runtime_agent\service

.\Install-RuntimeAgentService.ps1 -Token "change-me-to-a-long-random-token"
```

What install does:

- Copies `agent.py`, `start_agent.ps1`, and service scripts to `C:\OpenAS2\agent\`
- Writes `C:\OpenAS2\agent\agent.env` (token + host/port/root/python path)
- Downloads WinSW x64 into `C:\OpenAS2\agent\service\OpenAS2RuntimeAgent.exe` (if missing)
- Registers the Windows Service (does **not** start unless you pass `-Start`)
- Ensures inbound TCP **9475** firewall rule
- Does **not** modify OpenAS20/A/B or provisioned instances

Optional: `.\Install-RuntimeAgentService.ps1 -Token "..." -Start`  
Reinstall: add `-ForceReinstall`

### Start / stop / restart / status / uninstall

Run from `runtime_agent\service` or `C:\OpenAS2\agent\service` (elevated except status):

```powershell
.\Start-RuntimeAgentService.ps1
.\Stop-RuntimeAgentService.ps1
.\Restart-RuntimeAgentService.ps1
.\Get-RuntimeAgentServiceStatus.ps1
.\Uninstall-RuntimeAgentService.ps1
```

Equivalent built-ins:

```powershell
Start-Service -Name OpenAS2RuntimeAgent
Stop-Service -Name OpenAS2RuntimeAgent
Restart-Service -Name OpenAS2RuntimeAgent
Get-Service -Name OpenAS2RuntimeAgent
```

Uninstall removes the service registration. Deploy files/`agent.env` remain unless:

```powershell
.\Uninstall-RuntimeAgentService.ps1 -RemoveEnvFile
.\Uninstall-RuntimeAgentService.ps1 -RemoveDeployFiles
```

### Verify port 9475

```powershell
Get-NetTCPConnection -LocalPort 9475 -State Listen
netstat -ano | findstr :9475
.\Get-RuntimeAgentServiceStatus.ps1
```

Expect listen on `0.0.0.0:9475` (or `::` / specific addresses).

### Verify Frappe can reach `/v1/ping`

From Windows:

```powershell
$token = (Select-String -Path C:\OpenAS2\agent\agent.env -Pattern '^OPENAS2_AGENT_TOKEN=(.+)$').Matches.Groups[1].Value
Invoke-RestMethod -Uri http://127.0.0.1:9475/v1/ping -Method POST `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" -Body "{}"
```

From WSL (use your Windows host IP / configured URL):

```bash
curl -sS -X POST "http://172.18.48.1:9475/v1/ping" \
  -H "Authorization: Bearer change-me-to-a-long-random-token" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Or use `runtime_agent/probe_agent.py` / Desk Start/Stop on a provisioned instance.

Service logs: `C:\OpenAS2\agent\logs\` (WinSW roll logs + wrapper output).

### Troubleshooting

| Symptom | Check |
| --- | --- |
| Service will not install | Elevated PowerShell; `Get-Service OpenAS2RuntimeAgent`; antivirus blocking WinSW download |
| Service Running but port closed | `C:\OpenAS2\agent\logs\`; confirm `agent.env` has token; `OPENAS2_PYTHON` points at real `python.exe` |
| 401 from `/v1/ping` | Token in `agent.env` must match Frappe `openas2_runtime_agent_token` |
| 503 "token is not configured" | Empty/missing `OPENAS2_AGENT_TOKEN` in `agent.env` |
| WSL cannot connect | Firewall rule "OpenAS2 Runtime Agent"; use Windows host IP, not WSL `127.0.0.1` unless mirrored mode |
| Python not found under the service | Re-run install so `OPENAS2_PYTHON` is written with a full path |
| Manual and service both bound | Stop one: only one process can listen on 9475 |
| Need interactive debug | `.\Stop-RuntimeAgentService.ps1` then `..\start_agent.ps1 -Token "..."` |

## API

`POST http://127.0.0.1:9475/v1/action`  
Header: `Authorization: Bearer <token>`  
Body: `{"action":"start|stop|restart|status|health|logs","slug":"broker_abc_demo"}`

`GET/POST /v1/ping` — liveness.

## Tests (no service install required)

```bash
cd /home/laksh/openas2_bench/apps/openas2_manager
python -m unittest runtime_agent.tests.test_service_config
# or:
python runtime_agent/tests/test_service_config.py
```

## Out of scope (later)

- Installing each OpenAS2 Java instance as a Windows Service (`prunsrv` / per-instance service names)
- Changing Phase 1 provisioning
- Modifying Downloads `OpenAS20` / `OpenAS2A` / `OpenAS2B`
