# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Read-only OpenAS2 configuration viewer.

Reads ``config.xml`` and ``partnerships.xml`` from an OpenAS2 Instance's
configured home directory. Never writes to OpenAS2 files. Sensitive
attributes (passwords, secrets, private keys) are redacted before return.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import frappe
from frappe.utils import now_datetime

REDACTED = "********"

# Attribute / element names (case-insensitive substring match) to redact.
SENSITIVE_NAME_MARKERS = (
	"password",
	"passwd",
	"pwd",
	"secret",
	"private_key",
	"privatekey",
	"keystore_password",
	"db_pwd",
	"smtppwd",
	"api_key",
	"apikey",
	"token",
)

WRITE_MODES = frozenset({"w", "a", "x", "w+", "a+", "x+", "wb", "ab", "xb", "w+b", "a+b", "x+b"})


def is_sensitive_name(name: str | None) -> bool:
	if not name:
		return False
	lower = name.lower().replace("-", "_")
	return any(marker in lower for marker in SENSITIVE_NAME_MARKERS)


def redact_xml_text(raw: str) -> str:
	"""Redact sensitive attribute values in raw XML text."""
	if not raw:
		return raw

	def _replace_attr(match: re.Match) -> str:
		name = match.group(1)
		quote = match.group(2)
		if is_sensitive_name(name):
			return f"{name}={quote}{REDACTED}{quote}"
		return match.group(0)

	# name="value" or name='value'
	return re.sub(r"""([A-Za-z0-9_.:-]+)\s*=\s*(["'])(.*?)\2""", _replace_attr, raw, flags=re.DOTALL)


def safe_display_source(path: Path | str) -> str:
	"""Show a shortened configuration source path for the UI."""
	p = Path(path)
	parts = list(p.parts)
	if len(parts) >= 2:
		return str(Path(*parts[-2:]))
	return p.name or str(p)


def resolve_openas2_home(instance) -> Path:
	"""Resolve OpenAS2 home from instance fields (no hard-coded install map)."""
	home = (getattr(instance, "openas2_home", None) or "").strip()
	if home:
		return Path(home).expanduser()

	for candidate in (
		getattr(instance, "inbox_path", None),
		getattr(instance, "outbox_path", None),
	):
		derived = _derive_home_from_data_path(candidate)
		if derived:
			return derived

	frappe.throw(
		frappe._(
			"OpenAS2 Home is not set on instance {0}, and could not be derived from inbox/outbox paths."
		).format(frappe.bold(instance.name))
	)


def _derive_home_from_data_path(path_value: str | None) -> Path | None:
	if not path_value:
		return None
	path = Path(str(path_value).strip())
	parts = path.parts
	for idx, part in enumerate(parts):
		if part == "data" and idx > 0:
			return Path(*parts[:idx])
	return None


def read_text_readonly(path: Path) -> str:
	"""Read a file using read-only open. Never opens for write."""
	# Explicit mode 'r' — do not use any write mode.
	with path.open("r", encoding="utf-8", errors="replace") as handle:
		assert handle.mode.startswith("r") and not any(c in handle.mode for c in "wax+")
		return handle.read()


def detect_openas2_version(home: Path) -> str | None:
	lib = home / "lib"
	if lib.is_dir():
		jars = sorted(lib.glob("openas2-server-*.jar"))
		if jars:
			name = jars[-1].name
			# openas2-server-4.8.3.jar
			m = re.search(r"openas2-server-(.+)\.jar$", name, re.I)
			if m:
				return m.group(1)

	notes = home / "RELEASE-NOTES.md"
	if notes.is_file():
		try:
			text = read_text_readonly(notes)
			m = re.search(r"Version\s+([0-9]+(?:\.[0-9]+)*)", text)
			if m:
				return m.group(1)
		except OSError:
			pass
	return None


def parse_config_xml(raw: str) -> dict:
	"""Parse OpenAS2 config.xml into a safe summary dict (values already from XML)."""
	root = ET.fromstring(raw)
	props = root.find("properties")
	attrs = dict(props.attrib) if props is not None else {}

	# Never return sensitive property values in the structured summary.
	safe_props = {
		k: (REDACTED if is_sensitive_name(k) else v) for k, v in attrs.items()
	}

	def prop(*keys, default=None):
		for key in keys:
			if key in attrs:
				return attrs.get(key)
		return default

	http_port = prop("module.AS2ReceiverModule.http.port")
	https_port = prop("module.AS2ReceiverModule.https.port")
	mdn_http_port = prop("module.AS2MDNReceiverModule.http.port")
	mdn_https_port = prop("module.AS2MDNReceiverModule.https.port")
	http_enabled = prop("module.AS2ReceiverModule.http.enabled", default="true")
	https_enabled = prop("module.AS2ReceiverModule.https.enabled", default="true")
	mdn_http_enabled = prop("module.AS2MDNReceiverModule.http.enabled", default="true")
	mdn_https_enabled = prop("module.AS2MDNReceiverModule.https.enabled", default="true")

	keystore_path = prop("as2_keystore", default="")
	keystore_name = Path(str(keystore_path).replace("%home%/", "")).name if keystore_path else None

	certs = []
	for cert in root.findall("certificates"):
		certs.append(
			{
				"classname": cert.attrib.get("classname"),
				"identifier": cert.attrib.get("identifier"),
				"filename": cert.attrib.get("filename"),
				# password intentionally omitted / redacted
				"password": REDACTED if "password" in cert.attrib else None,
			}
		)

	primary_factory = certs[0]["classname"] if certs else None
	keystore_type = None
	if primary_factory and "PKCS12" in primary_factory:
		keystore_type = "PKCS12"
	elif keystore_name and keystore_name.lower().endswith(".p12"):
		keystore_type = "PKCS12"
	elif keystore_name and keystore_name.lower().endswith(".jks"):
		keystore_type = "JKS"

	storage = prop("storageBaseDir", default="")
	inbox_pattern = prop("module.MessageFileModule.filename", default="")
	outbox_pattern = prop("pollerConfigBase.outboxdir", default="")
	health_port = prop("module.HealthCheckModule.port")
	tracking_port = prop("msg_tracking.tcp_server_port")

	mdn_enabled = (
		str(mdn_http_enabled).lower() == "true" or str(mdn_https_enabled).lower() == "true"
	)
	async_mdn_url = prop("as2_async_mdn_url", default="")
	mdn_mode = "Asynchronous" if async_mdn_url else "Synchronous"

	return {
		"properties_safe": safe_props,
		"http_enabled": str(http_enabled).lower() == "true",
		"http_port": http_port,
		"https_enabled": str(https_enabled).lower() == "true",
		"https_port": https_port,
		"mdn_enabled": mdn_enabled,
		"mdn_mode": mdn_mode,
		"mdn_http_port": mdn_http_port,
		"mdn_https_port": mdn_https_port,
		"health_port": health_port,
		"tracking_port": tracking_port,
		"certificate_factory": primary_factory,
		"keystore_type": keystore_type,
		"keystore_name": keystore_name,
		"certificates": certs,
		"storage_base_dir": storage,
		"inbox_pattern": inbox_pattern,
		"outbox_pattern": outbox_pattern,
	}


def parse_partnerships_xml(raw: str, local_as2_id: str | None = None) -> dict:
	root = ET.fromstring(raw)
	partners = {}
	for partner in root.findall("partner"):
		name = partner.attrib.get("name")
		if not name:
			continue
		partners[name] = {
			"name": name,
			"as2_id": partner.attrib.get("as2_id"),
			"x509_alias": partner.attrib.get("x509_alias"),
			"email": partner.attrib.get("email"),
		}

	rows = []
	for partnership in root.findall("partnership"):
		pname = partnership.attrib.get("name") or ""
		sender_el = partnership.find("sender")
		receiver_el = partnership.find("receiver")
		sender_name = sender_el.attrib.get("name") if sender_el is not None else None
		receiver_name = receiver_el.attrib.get("name") if receiver_el is not None else None

		attrs = {}
		for attr in partnership.findall("attribute"):
			aname = attr.attrib.get("name")
			if aname:
				attrs[aname] = attr.attrib.get("value")

		poller = partnership.find("pollerConfig")
		poller_enabled = None
		if poller is not None:
			poller_enabled = str(poller.attrib.get("enabled", "true")).lower() == "true"

		sender_as2 = partners.get(sender_name, {}).get("as2_id") if sender_name else None
		receiver_as2 = partners.get(receiver_name, {}).get("as2_id") if receiver_name else None

		mdn_options = attrs.get("as2_mdn_options") or ""
		mdn_to = attrs.get("as2_mdn_to")
		if mdn_options.strip().lower() == "none":
			mdn_label = "Disabled"
		elif mdn_to or mdn_options:
			mdn_label = "Enabled"
		else:
			mdn_label = "—"

		if attrs.get("as2_url"):
			status = "Outbound"
		elif attrs.get("store_received_file_to"):
			status = "Inbound"
		else:
			status = "Configured"

		if poller_enabled is True:
			status = f"{status} / Poller"
		elif poller_enabled is False:
			status = f"{status} / Poller off"

		rows.append(
			{
				"partnership_name": pname,
				"partner_name": receiver_name or sender_name,
				"local_as2_id": sender_as2,
				"remote_as2_id": receiver_as2,
				"remote_url": attrs.get("as2_url") or "—",
				"encryption": attrs.get("encrypt") or "—",
				"signing": attrs.get("sign") or "—",
				"mdn": mdn_label,
				"status": status,
			}
		)

	return {"partners": list(partners.values()), "partnerships": rows}


@frappe.whitelist()
def list_instances_for_viewer() -> list[dict]:
	"""Return OpenAS2 Instance options for the configuration viewer."""
	from openas2_manager.access import get_allowed_instance_names

	filters = {}
	allowed = get_allowed_instance_names()
	if allowed is not None:
		if not allowed:
			return []
		filters["name"] = ["in", allowed]

	rows = frappe.get_all(
		"OpenAS2 Instance",
		fields=["name", "instance_name", "instance_type", "as2_id", "status", "host", "openas2_home"],
		filters=filters,
		order_by="instance_type asc, instance_name asc",
	)
	return rows


@frappe.whitelist()
def get_instance_configuration(instance_name: str) -> dict:
	"""Read and return redacted OpenAS2 configuration for an instance.

	Read-only: never writes to config.xml, partnerships.xml, or keystores.
	"""
	if not instance_name:
		frappe.throw(frappe._("Please select an OpenAS2 Instance."))

	from openas2_manager.access import assert_instance_access

	assert_instance_access(instance_name)

	instance = frappe.get_doc("OpenAS2 Instance", instance_name)
	home = resolve_openas2_home(instance)
	config_dir = home / "config"
	config_path = config_dir / "config.xml"
	partnerships_path = config_dir / "partnerships.xml"

	last_read = now_datetime()
	result = {
		"read_only": True,
		"writes_performed": False,
		"last_read": str(last_read),
		"configuration_source": safe_display_source(config_dir),
		"openas2_home_display": safe_display_source(home),
		"instance": {
			"name": instance.name,
			"instance_name": instance.instance_name,
			"instance_type": instance.instance_type,
			"as2_id": instance.as2_id,
			"status": instance.status,
			"host": instance.host,
			"port": instance.port,
			"protocol": instance.protocol,
			"mdn_enabled": instance.mdn_enabled,
			"inbox_path": instance.inbox_path,
			"outbox_path": instance.outbox_path,
		},
		"openas2_version": detect_openas2_version(home),
		"errors": [],
		"server": {},
		"mdn": {},
		"certificate": {},
		"directories": {
			"inbox": instance.inbox_path,
			"outbox": instance.outbox_path,
		},
		"partnerships": [],
		"partners": [],
		"raw": {
			"config_xml": None,
			"partnerships_xml": None,
			"config_error": None,
			"partnerships_error": None,
		},
	}

	# --- config.xml ---
	if not config_path.exists():
		msg = "Configuration file not found."
		result["errors"].append(msg)
		result["raw"]["config_error"] = msg
	else:
		try:
			raw_config = read_text_readonly(config_path)
			redacted = redact_xml_text(raw_config)
			result["raw"]["config_xml"] = redacted
			parsed = parse_config_xml(raw_config)
			result["server"] = {
				"http_host": instance.host,
				"http_port": parsed.get("http_port"),
				"http_enabled": parsed.get("http_enabled"),
				"https_host": instance.host,
				"https_port": parsed.get("https_port"),
				"https_enabled": parsed.get("https_enabled"),
			}
			result["mdn"] = {
				"mdn_enabled": parsed.get("mdn_enabled"),
				"mdn_mode": parsed.get("mdn_mode"),
				"mdn_http_port": parsed.get("mdn_http_port"),
				"mdn_https_port": parsed.get("mdn_https_port"),
				# Prefer instance flag if set, else config-derived
				"instance_mdn_enabled": bool(instance.mdn_enabled),
			}
			result["certificate"] = {
				"certificate_factory": parsed.get("certificate_factory"),
				"keystore_type": parsed.get("keystore_type"),
				"keystore_name": parsed.get("keystore_name"),
			}
			# Prefer patterns from config for directory display when instance paths empty
			if not result["directories"]["inbox"] and parsed.get("inbox_pattern"):
				result["directories"]["inbox"] = parsed["inbox_pattern"]
			if not result["directories"]["outbox"] and parsed.get("outbox_pattern"):
				result["directories"]["outbox"] = parsed["outbox_pattern"]
		except PermissionError as exc:
			msg = f"Permission denied reading configuration file: {exc}"
			result["errors"].append(msg)
			result["raw"]["config_error"] = msg
		except OSError as exc:
			msg = f"Unable to read configuration file: {exc}"
			result["errors"].append(msg)
			result["raw"]["config_error"] = msg
		except ET.ParseError as exc:
			msg = f"Invalid config.xml XML: {exc}"
			result["errors"].append(msg)
			result["raw"]["config_error"] = msg

	# --- partnerships.xml ---
	if not partnerships_path.exists():
		msg = "Partnership configuration not found."
		result["errors"].append(msg)
		result["raw"]["partnerships_error"] = msg
	else:
		try:
			raw_partnerships = read_text_readonly(partnerships_path)
			result["raw"]["partnerships_xml"] = redact_xml_text(raw_partnerships)
			parsed_p = parse_partnerships_xml(raw_partnerships, local_as2_id=instance.as2_id)
			result["partners"] = parsed_p["partners"]
			result["partnerships"] = parsed_p["partnerships"]
		except PermissionError as exc:
			msg = f"Permission denied reading partnership configuration: {exc}"
			result["errors"].append(msg)
			result["raw"]["partnerships_error"] = msg
		except OSError as exc:
			msg = f"Unable to read partnership configuration: {exc}"
			result["errors"].append(msg)
			result["raw"]["partnerships_error"] = msg
		except ET.ParseError as exc:
			msg = f"Invalid partnerships.xml XML: {exc}"
			result["errors"].append(msg)
			result["raw"]["partnerships_error"] = msg

	# Final safety: ensure no obvious secrets slipped into JSON payload keys
	_assert_no_plaintext_secrets(result)
	return result


def _assert_no_plaintext_secrets(payload: dict) -> None:
	"""Best-effort guard — strip accidental password fields from nested dicts."""
	stack = [payload]
	while stack:
		obj = stack.pop()
		if isinstance(obj, dict):
			for key in list(obj.keys()):
				if is_sensitive_name(key) and obj[key] not in (None, REDACTED, "—"):
					# Allow only redacted or non-secret structural values
					val = obj[key]
					if isinstance(val, str) and val != REDACTED and "password" in key.lower():
						obj[key] = REDACTED
				elif isinstance(obj[key], (dict, list)):
					stack.append(obj[key])
		elif isinstance(obj, list):
			stack.extend(obj)


def _to_int_port(value) -> int | None:
	if value in (None, ""):
		return None
	try:
		port = int(str(value).strip())
	except (TypeError, ValueError):
		return None
	if 1 <= port <= 65535:
		return port
	return None


def wsl_home_to_windows(home: Path | str) -> str | None:
	"""Map /mnt/c/... to C:\\... for display on External Windows installs."""
	text = str(home).replace("\\", "/")
	if text.startswith("/mnt/c/") or text.startswith("/mnt/c"):
		rest = text[len("/mnt/c") :].lstrip("/")
		return "C:\\" + rest.replace("/", "\\")
	return None


@frappe.whitelist()
def sync_instance_from_config(instance_name: str) -> dict:
	"""Load listener ports from instance config.xml into the OpenAS2 Instance DocType.

	Updates Frappe metadata only. Does not modify config.xml or restart OpenAS2.
	"""
	if not instance_name:
		frappe.throw(frappe._("Please select an OpenAS2 Instance."))

	from openas2_manager.access import assert_instance_access, is_system_manager

	assert_instance_access(instance_name)
	if not (is_system_manager() or frappe.has_permission("OpenAS2 Instance", "write", instance_name)):
		frappe.throw(frappe._("Not permitted to update this OpenAS2 Instance."), frappe.PermissionError)

	instance = frappe.get_doc("OpenAS2 Instance", instance_name)
	home = resolve_openas2_home(instance)
	config_path = home / "config" / "config.xml"
	if not config_path.is_file():
		frappe.throw(
			frappe._("config.xml not found under {0}.").format(frappe.bold(str(config_path)))
		)

	raw = read_text_readonly(config_path)
	parsed = parse_config_xml(raw)

	http_port = _to_int_port(parsed.get("http_port"))
	https_port = _to_int_port(parsed.get("https_port"))
	mdn_http_port = _to_int_port(parsed.get("mdn_http_port"))
	mdn_https_port = _to_int_port(parsed.get("mdn_https_port"))
	health_port = _to_int_port(parsed.get("health_port"))
	tracking_port = _to_int_port(parsed.get("tracking_port"))

	instance.http_enabled = 1 if parsed.get("http_enabled") else 0
	instance.https_enabled = 1 if parsed.get("https_enabled") else 0

	# Prefer HTTPS as primary listener when enabled; else HTTP.
	if parsed.get("https_enabled") and https_port:
		instance.protocol = "HTTPS"
		instance.port = https_port
	elif http_port:
		instance.protocol = "HTTP"
		instance.port = http_port

	if http_port is not None:
		instance.http_port = http_port
	if https_port is not None:
		instance.https_port = https_port
	if mdn_http_port is not None:
		instance.mdn_http_port = mdn_http_port
	if mdn_https_port is not None:
		instance.mdn_https_port = mdn_https_port
	if health_port is not None:
		instance.health_port = health_port
	if tracking_port is not None:
		instance.tracking_port = tracking_port

	# MDN listener enables — parse from raw properties when available.
	props = parsed.get("properties_safe") or {}
	mdn_http_en = str(props.get("module.AS2MDNReceiverModule.http.enabled", "true")).lower() == "true"
	mdn_https_en = str(props.get("module.AS2MDNReceiverModule.https.enabled", "true")).lower() == "true"
	instance.mdn_http_enabled = 1 if mdn_http_en else 0
	instance.mdn_https_enabled = 1 if mdn_https_en else 0
	instance.mdn_enabled = 1 if parsed.get("mdn_enabled") else 0
	instance.mdn_mode = parsed.get("mdn_mode") or "Synchronous"

	async_url = props.get("as2_async_mdn_url") or ""
	if async_url and async_url != REDACTED:
		# Resolve common port placeholder for display
		if mdn_http_port and "$properties.async_mdn_receiver_port$" in async_url:
			async_url = async_url.replace(
				"$properties.async_mdn_receiver_port$", str(mdn_http_port)
			)
		instance.async_mdn_url = async_url

	ks = props.get("as2_keystore") or ""
	if ks and ks != REDACTED:
		instance.as2_keystore_path = ks
	ssl_ks = props.get("ssl_keystore") or ""
	if ssl_ks and ssl_ks != REDACTED:
		instance.ssl_keystore_path = ssl_ks

	win = wsl_home_to_windows(home)
	if win:
		instance.windows_home = win

	# Prefer keystore alias from partnerships local partner when AS2 ID matches.
	partnerships_path = home / "config" / "partnerships.xml"
	if partnerships_path.is_file():
		try:
			partners = parse_partnerships_xml(
				read_text_readonly(partnerships_path), local_as2_id=instance.as2_id
			).get("partners") or []
			for partner in partners:
				if partner.get("as2_id") == instance.as2_id and partner.get("x509_alias"):
					instance.x509_alias = partner["x509_alias"]
					instance.certificate_status = "Configured"
					break
		except (OSError, ET.ParseError):
			pass

	instance.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"name": instance.name,
		"instance_type": instance.instance_type,
		"as2_id": instance.as2_id,
		"openas2_home": str(home),
		"windows_home": instance.windows_home,
		"protocol": instance.protocol,
		"port": instance.port,
		"http_enabled": instance.http_enabled,
		"https_enabled": instance.https_enabled,
		"http_port": instance.http_port,
		"https_port": instance.https_port,
		"mdn_mode": instance.mdn_mode,
		"mdn_http_enabled": instance.mdn_http_enabled,
		"mdn_https_enabled": instance.mdn_https_enabled,
		"published_as2_url": instance.published_as2_url,
		"message": frappe._(
			"Loaded listener, MDN, and keystore settings from config.xml into this Instance form. "
			"OpenAS2 files were not modified."
		),
	}
