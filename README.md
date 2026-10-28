### OpenAS2 Manager

Central OpenAS2 Management Web UI for Shipper, Broker, and Carrier TMS systems.

This app runs on its **own Frappe bench** (`openas2_bench`, site `openas2.local`). It does **not** replace or modify the existing Shipper, Broker, or Carrier TMS applications, and it does **not** redesign the OpenAS2 server. Its purpose is a single web UI to manage and monitor OpenAS2 configuration across all three TMS systems.

### Installation

```bash
cd /home/laksh/openas2_bench
bench get-app /path/to/openas2_manager   # if installing from a remote/path
bench --site openas2.local install-app openas2_manager
bench --site openas2.local migrate
```

### AS2 Partner Management

**AS2 Partner** represents a trading partner that participates in AS2 messaging (Shipper, Broker, or Carrier). Records store identity and connection *configuration* used by the management UI.

This module is **configuration / UI only** for messaging (no live send/receive yet).

#### Fields

| Field | Meaning |
| --- | --- |
| **Partner Name** | Display name of the trading partner |
| **AS2 ID** | Unique AS2 identifier (also used as the document name) |
| **Partner Type** | `Shipper`, `Broker`, or `Carrier` |
| **AS2 URL** | Partner AS2 endpoint URL (stored only; not called yet) |
| **Encryption Enabled** | Whether encryption is expected for this partner |
| **Signing Enabled** | Whether signing is expected for this partner |
| **MDN Enabled** | Whether MDNs are expected |
| **MDN Mode** | `Synchronous` or `Asynchronous` (required when MDN is enabled) |
| **Certificate** | Link to **AS2 Certificate** (public cert metadata) |
| **Status** | `Active` or `Inactive` (defaults to Active) |
| **Description** | Free-text notes |

#### Seed demo partners (idempotent)

```bash
bench --site openas2.local execute openas2_manager.setup.seed.seed_demo_partners
```

### AS2 Certificate Management

**AS2 Certificate** stores public certificate metadata for Shipper / Broker / Carrier partners.

#### Fields

| Field | Meaning |
| --- | --- |
| **Certificate Name** | Unique display / document name |
| **Certificate Type** | `Signing`, `Encryption`, or `Both` |
| **TMS** | Owning system: `Shipper`, `Broker`, or `Carrier` |
| **Common Name** | Certificate CN |
| **Valid From / Valid Until** | Validity window |
| **Status** | `Active`, `Expired`, or `Revoked` (default Active; auto-Expired when past Valid Until, never overwrites Revoked) |
| **Expiry Information** | Read-only summary of remaining / elapsed days |
| **Certificate File** | Attach **public** certificate only (`.cer` / `.crt` / `.pem`) |
| **Description** | Free-text notes |

#### Security rules

- Private keys are **not** stored in Data/Text fields
- Private key contents are **not** shown in the UI
- Keystore passwords are **not** hard-coded in this app
- Generation API responses never include private keys or passwords
- Do not attach PKCS12 files that contain private keys to **Certificate File**

#### Certificate generation (pending integration)

Desk button **Generate Certificate** calls:

`openas2_manager.certificates.generation.request_certificate_generation`

Inspection of the existing OpenAS2 installs shows they use:

- `org.openas2.cert.PKCS12CertificateFactory`
- PKCS12 keystores (`.p12`), e.g. `broker_as2.p12`
- Java `keytool` + `bin/import_alias_from_keystore` for alias import
- Partner `x509_alias` in `partnerships.xml`

**Current behavior:** the button reports integration status as **pending**. It does **not** invent certificates and does **not** write to the live OpenAS2 keystore / config.

To enable real generation later (recommended):

1. Install / expose Java `keytool` to the Frappe host
2. Configure a managed keystore path via site config (and password via environment variable — never in DocType fields)
3. Generate PKCS12 entries with `keytool -genkeypair -storetype PKCS12`
4. Import aliases with OpenAS2’s import script **without** modifying production config until reviewed

#### List view & filters

- List columns: Certificate Name, Certificate Type, TMS, Common Name, Valid Until, Status
- Filters: Certificate Type, TMS, Status
- Search: Certificate Name, Common Name, TMS

#### Tests

```bash
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2_manager.doctype.as2_certificate.test_as2_certificate
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2_manager.doctype.as2_partner.test_as2_partner
```

### OpenAS2 Instance Configuration

**OpenAS2 Instance** stores central UI metadata for each local OpenAS2 server (Shipper / Broker / Carrier).

#### Create OpenAS2 Communication (Phase 1)

From **OpenAS2 Instance** list: **Create OpenAS2 Communication** (System Manager).

Provisions an isolated runtime home under `C:\OpenAS2\instances\<slug>\` (WSL: `/mnt/c/OpenAS2/instances/<slug>/`):

- Allocates unused HTTP / HTTPS / MDN / tracking / health ports (legacy OpenAS20/A/B ports reserved)
- Writes `config/`, `data/`, `logs/`, `keystore/` (no full OpenAS2 tree copy)
- Generates `config.xml` + minimal `partnerships.xml` (HTTP enabled; HTTPS disabled until certs)
- Creates **OpenAS2 Instance** with `lifecycle_status=Stopped`
- Audits via **OpenAS2 Provisioning Log**

Does **not** start Java, does **not** generate PKCS12, does **not** modify Downloads OpenAS20/A/B or TMS apps.

Optional site_config keys: `openas2_windows_root`, `openas2_wsl_root`, `openas2_instances_root`, `openas2_runtime_root`.

```bash
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2.test_provisioning
```

### Runtime Agent control (Phase 2)

Manager-provisioned instances are controlled by a **Windows Runtime Agent** (not by Frappe shelling out to `.bat` files).

| Action | Desk | API |
| --- | --- | --- |
| Start / Stop / Restart | Runtime menu (confirm) | `runtime_control` |
| Status / Health / Logs | Runtime menu | `runtime_status` / `runtime_health` / `runtime_logs` |

Setup:

1. Copy jars: `bash apps/openas2_manager/runtime_agent/prepare_runtime_lib.sh` (or Desk prepare later)
2. Start the agent on Windows (pick one):
   - **Service (Phase 2A):** elevated `runtime_agent/service/Install-RuntimeAgentService.ps1 -Token <secret>` then `Start-RuntimeAgentService.ps1` (see `runtime_agent/README.md`)
   - **Manual fallback:** `runtime_agent/start_agent.ps1 -Token <secret>`
3. `bench --site openas2.local set-config openas2_runtime_agent_token <secret>`
4. From WSL set URL to the Windows host (often `http://172.x.x.1:9475`); Manager also auto-detects the WSL default gateway when URL is localhost
5. Place `keystore/as2.p12` on the instance before Start (Phase 3 will generate PKCS12)

Only the **Runtime Agent** may be installed as a Windows Service in Phase 2A. OpenAS2 Java instances still use PID/process control. Does **not** control legacy OpenAS20/A/B.

```bash
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2.test_runtime_control
```

#### Discovered local installs (read-only)

| Role | Home | Version | HTTPS port | HTTP port | Keystore | Inbox (site config) |
| --- | --- | --- | --- | --- | --- | --- |
| Shipper | `/mnt/c/Users/laksh/Downloads/OpenAS20` | jar `4.8.3` (RELEASE-NOTES `4.8.2`) | 12443 | 12080 | `shipper_as2.p12` | `.../OpenAS20/data/inbox/SHIPPER_AS2ID/inbox` |
| Broker | `/mnt/c/Users/laksh/Downloads/OpenAS2A` | jar `4.8.3` | 10443 | 10080 | `broker_as2.p12` | `.../OpenAS2A/data/inbox/BROKER_AS2ID/inbox` |
| Carrier | `/mnt/c/Users/laksh/Downloads/OpenAS2B` | jar `4.8.3` | 11443 | 11080 | `carrier_as2.p12` | `.../OpenAS2B/data/inbox/CARRIER_AS2ID/inbox` |

- Config: `{home}/config/config.xml`, partners: `{home}/config/partnerships.xml`
- Certificates: `PKCS12CertificateFactory` + SSL JKS (`ssl_certs.jks`)
- MDN: sync options in partnerships; async MDN HTTP ports 10081 / 11081 / 12081
- Outbox poller: `{storageBaseDir}/outbox/{receiver.as2_id}`

#### Fields

| Field | Meaning |
| --- | --- |
| **Instance Name** | Unique name (document name) |
| **Instance Type** | Shipper / Broker / Carrier |
| **AS2 ID** | Unique AS2 identifier for this instance |
| **Host / Port / Protocol** | Listener endpoint (HTTPS default) |
| **Inbox Path / Outbox Path** | Filesystem paths (metadata only) |
| **MDN Enabled** | Whether MDN is expected (default on) |
| **Status** | Active / Inactive / Error |
| **Connection Status** | Unknown / Connected / Failed (read-only; set by Test Connection) |
| **Last Tested** | Timestamp of last Test Connection (read-only) |
| **Description** | Notes |

No private keys, certificate passwords, DB passwords, or keystore passwords are stored on this DocType.

#### Test Connection

Button calls `openas2_manager.openas2.connection.test_instance_connection`.

- Validates host/port
- Performs a short **TCP connect** only
- Does **not** send EDI, alter config, or restart OpenAS2
- `Connected` = TCP port accepted a connection (not full AS2/TLS verification)
- Records `connection_status` and `last_tested`

#### Seed discovered instances (idempotent)

```bash
bench --site openas2.local execute openas2_manager.setup.seed_instances.seed_demo_instances
```

#### Tests

```bash
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2_manager.doctype.openas2_instance.test_openas2_instance
```

### OpenAS2 Configuration Viewer (read-only)

Desk page: **OpenAS2 Configuration** (`/app/openas2-configuration`)

Select a configured **OpenAS2 Instance** (Shipper / Broker / Carrier). The viewer reads that instance’s `openas2_home` (or derives home from inbox/outbox paths) and loads:

- `{home}/config/config.xml`
- `{home}/config/partnerships.xml`

#### What it shows

- Instance summary (name, type, AS2 ID, detected OpenAS2 version, status)
- HTTP / HTTPS listener ports from `config.xml`
- MDN ports / mode
- Certificate factory + keystore type/name (not passwords)
- Inbox / outbox paths from the Instance record
- Partnerships table (local/remote AS2 IDs, URL, encrypt, sign, MDN, status)
- **View Raw Configuration** with redacted XML
- **Last Read** timestamp and shortened **Configuration Source**

#### Safety

- **Read-only** — never writes `config.xml`, `partnerships.xml`, or keystores
- Does **not** restart OpenAS2
- Does **not** require OpenAS2 to be running
- Passwords / private keys / keystore passwords are **redacted** (`********`)
- Future configuration editing requires a separate reviewed implementation

#### Tests

```bash
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2.test_config_viewer
```

### OpenAS2 Partnership Configuration Management

Desk page: **OpenAS2 Partnerships** (`/app/openas2-partnerships`)

Workflow:

1. Create/edit an **OpenAS2 Partnership** in Frappe (**Save does not write XML**)
2. **Preview Configuration Change** — builds proposed `partnerships.xml`, stores an **OpenAS2 Configuration Change** audit row (`Proposed`), shows CURRENT / PROPOSED / DIFF
3. Administrator explicitly clicks **Apply**
4. System validates XML → timestamped backup under `{home}/config/backups/` → atomic write → re-parse verify
5. **OpenAS2 is never restarted automatically**

#### DocTypes

- **OpenAS2 Partnership** — proposed partnership settings (Draft/Active/Inactive)
- **OpenAS2 Configuration Change** — audit of Proposed / Applied / Failed / Rolled Back

#### Certificate links

OpenAS2 `partnerships.xml` references certificates via partner `x509_alias` (e.g. `broker`), **not** via Frappe AS2 Certificate documents. Therefore `local_certificate` / `remote_certificate` Links were **not** added. Use:

- `local_x509_alias` / `remote_x509_alias`
- `local_partner_name` / `remote_partner_name`

#### Safety

- No silent apply on DocType save
- Path traversal blocked — writes only under instance `openas2_home`
- Passwords / private keys redacted in proposals
- Failed apply attempts restore from backup when possible
- Read-only Configuration Viewer remains unchanged

#### Tests

```bash
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2.test_partnership_config
```

### OpenAS2 Restart Helper (Step 6)

Explicit **Restart OpenAS2** for a selected instance. Never runs automatically after Preview, Apply, or DocType save.

#### Safety

- System Manager only + confirmation dialog required
- Discovers control capability from instance `openas2_home` (fixed `bin/start-openas2.sh` + `bin/OpenAS2.pid`)
- No UI-supplied commands, paths, or PIDs
- If this Frappe host cannot safely control the process (e.g. Windows-mounted install without Linux Java): **Not Available** + diagnostics — never fakes success
- Result distinguishes Process / TCP / **AS2 Protocol: Not Verified**
- Audit: **OpenAS2 Restart Log**

#### Tests

```bash
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2.test_restart
```

### OpenAS2 Messages & Logs Monitoring (Step 7)

Read-only central monitoring of AS2/EDI activity across Shipper / Broker / Carrier OpenAS2 instances.

#### Sources (discovered, never modified)

- `{openas2_home}/logs/log-YYYYMMDD.txt` (Logback lines + AS2 Message-IDs)
- Inbox: `data/inbox/{local}/inbox/` (+ `processed/`, `error/`)
- Outbox errors: `data/outbox/error/YYYY-MM-DD/{remote}/`
- Soft link to TMS **EDI Document** only if that DocType exists on this site (it normally does not)
- **TMS EDI sync (all TMS):** on Refresh, pulls `EDI Document` metadata from each configured Shipper / Broker / Carrier / CompanyC Frappe site into read-only **OpenAS2 EDI Document**, shown on Monitoring → **EDI Transactions**. Opens the document on the remote TMS desk (absolute URL). Does not install TMS apps on this bench.

#### TMS site_config

In `sites/openas2.local/site_config.json`:

```json
"tms_sites": {
  "Shipper": {
    "url": "http://shipper.local:8000",
    "api_key": "<frappe api key>",
    "api_secret": "<frappe api secret>"
  },
  "Broker": {
    "url": "http://broker.local:8000",
    "api_key": "...",
    "api_secret": "..."
  },
  "Carrier": {
    "url": "http://carrier.local:8000",
    "api_key": "...",
    "api_secret": "..."
  }
}
```

Optional: set **TMS Site URL** on each **OpenAS2 Instance** (overrides `tms_sites.<TMS>.url`). Create API keys on each TMS for a user that can read `EDI Document`.

#### UI

| Page | Route |
| --- | --- |
| Dashboard | `/app/openas2-dashboard` |
| Messages | `/app/openas2-messages` |
| Errors | `/app/openas2-errors` |

**Refresh** re-reads OpenAS2 sources **and** syncs EDI Documents from all configured TMS sites. A **cron job every minute** also runs the same sync so sent/received EDI docs appear without clicking Refresh. The Monitoring page auto-reloads every 15s and listens for realtime updates.

Optional **instant push** from each TMS (on EDI Document insert/update):

```json
"openas2_tms_webhook_token": "shared-secret"
```

TMS calls:

```
POST {openas2_manager_url}/api/method/openas2_manager.openas2.tms_edi.ingest_tms_edi_document
Header: X-OpenAS2-Token: shared-secret
Body: tms=Shipper&name=EDI-0001&file_name=...&status=...&direction=Outbound&as2_message_id=...
```

No resend/delete/edit of messages. No OpenAS2 config or restart from this UI.

#### Tests

```bash
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2.test_monitoring
bench --site openas2.local run-tests --app openas2_manager --module openas2_manager.openas2.test_tms_edi
```

### Planned later (not in this step)

- Certificate generation / keystore import into OpenAS2
- Automatic polling / live EDI send-receive from this UI
- Message resend

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/openas2_manager
pre-commit install
```

### License

mit
