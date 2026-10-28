# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Phase 1: provision an isolated OpenAS2 instance from the Manager UI.

Creates filesystem layout + config under the managed instances root.
Does NOT:
- start / stop / restart OpenAS2
- modify existing OpenAS20 / OpenAS2A / OpenAS2B installs
- generate PKCS12 certificates
- touch TMS applications
- execute user-supplied shell commands
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import frappe
from frappe.utils import cint, now_datetime

from openas2_manager.openas2 import config_generator as cg
from openas2_manager.openas2 import port_allocator
from openas2_manager.openas2.paths import (
	assert_under_directory,
	get_instances_root,
	get_runtime_root,
	instance_paths,
	slugify_instance_name,
	to_windows_path,
	windows_instances_root,
)

ALLOWED_TYPES = frozenset({"Shipper", "Broker", "Carrier"})
AS2_ID_RE_MSG = "AS2 ID may contain letters, digits, underscore, and hyphen only."


def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(
			frappe._("Only System Managers may provision OpenAS2 instances."),
			frappe.PermissionError,
		)


def _validate_as2_id(as2_id: str) -> str:
	value = (as2_id or "").strip()
	if not value:
		frappe.throw(frappe._("AS2 ID is required."))
	if len(value) > 128:
		frappe.throw(frappe._("AS2 ID is too long."))
	for ch in value:
		if not (ch.isalnum() or ch in "_-"):
			frappe.throw(frappe._(AS2_ID_RE_MSG))
	return value


def _validate_instance_name(name: str) -> str:
	value = (name or "").strip()
	if not value:
		frappe.throw(frappe._("Instance Name is required."))
	if len(value) > 140:
		frappe.throw(frappe._("Instance Name is too long."))
	return value


def _ensure_managed_roots() -> None:
	instances = get_instances_root()
	runtime = get_runtime_root()
	instances.mkdir(parents=True, exist_ok=True)
	runtime.mkdir(parents=True, exist_ok=True)
	readme = runtime / "README.txt"
	if not readme.is_file():
		readme.write_text(
			"Shared OpenAS2 runtime template (lib/, bin helpers).\n"
			"Phase 1 does not copy jars automatically.\n"
			"Link or copy OpenAS2 4.8.3 lib/ here before starting runtimes (Phase 2).\n"
			"Do not store instance config/data here.\n",
			encoding="utf-8",
		)


def _create_directory_tree(paths: dict[str, Path]) -> list[str]:
	created: list[str] = []
	home = paths["home"]
	# home was already validated under get_instances_root() in instance_paths()
	instances_root = home.parent
	for key in (
		"home",
		"config",
		"data",
		"logs",
		"keystore",
		"inbox",
		"outbox",
		"resend",
		"temp",
		"pending_mdn",
		"pending_mdn_info",
	):
		path = paths[key]
		if key == "home":
			assert_under_directory(instances_root, path)
		else:
			assert_under_directory(home, path)
		path.mkdir(parents=True, exist_ok=True)
		created.append(str(path))

	# Nested data helpers used by OpenAS2 modules
	for extra in (
		paths["data"] / "inbox" / "error",
		paths["data"] / "outbox" / "error",
		paths["data"] / "resend" / "error",
		paths["config"] / "DB",
		paths["config"] / "backups",
	):
		assert_under_directory(home, extra)
		extra.mkdir(parents=True, exist_ok=True)
		created.append(str(extra))
	return created


def _write_keystore_placeholder(keystore_dir: Path, home: Path, as2_id: str) -> None:
	assert_under_directory(home, keystore_dir)
	readme = keystore_dir / "README.txt"
	readme.write_text(
		f"Keystore directory for AS2 ID {as2_id}.\n"
		"Phase 1 does not generate PKCS12/JKS files.\n"
		"Expected later: as2.p12 (PKCS12CertificateFactory).\n"
		"HTTPS remains disabled until certificates are provisioned.\n",
		encoding="utf-8",
	)


def _write_instance_readme(home: Path, *, slug: str, as2_id: str, ports: dict) -> None:
	assert_under_directory(home.parent, home)
	(home / "README.txt").write_text(
		"OpenAS2 Manager provisioned instance (Phase 1).\n"
		f"slug={slug}\n"
		f"as2_id={as2_id}\n"
		f"http_port={ports['http_port']}\n"
		f"https_port={ports['https_port']} (HTTPS disabled until certs)\n"
		f"mdn_http_port={ports['mdn_http_port']}\n"
		f"windows_path={to_windows_path(home)}\n"
		"Status: Stopped — runtime not started by provisioning.\n"
		"Existing Downloads\\OpenAS20|A|B installs were not modified.\n",
		encoding="utf-8",
	)


def _validate_generated_xml(config_xml: str, partnerships_xml: str) -> None:
	try:
		ET.fromstring(config_xml)
	except ET.ParseError as exc:
		frappe.throw(frappe._("Generated config.xml is invalid: {0}").format(exc))
	try:
		ET.fromstring(partnerships_xml)
	except ET.ParseError as exc:
		frappe.throw(frappe._("Generated partnerships.xml is invalid: {0}").format(exc))


def _partner_name_for(instance_type: str, instance_name: str) -> str:
	# OpenAS2 partner @name — keep readable, no path chars
	base = instance_name.strip().replace("/", "-").replace("\\", "-")
	return base or instance_type


def _x509_alias_for(slug: str) -> str:
	alias = slug.replace("-", "_")[:64]
	return alias or "local"


def _insert_provisioning_log(**fields) -> str:
	doc = frappe.get_doc({"doctype": "OpenAS2 Provisioning Log", **fields})
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def preview_port_allocation(instance_type: str) -> dict:
	"""Return a candidate port set without writing (System Manager)."""
	_require_system_manager()
	if instance_type not in ALLOWED_TYPES:
		frappe.throw(frappe._("Instance Type must be Shipper, Broker, or Carrier."))
	ports = port_allocator.allocate_ports_for_type(instance_type)
	return {"instance_type": instance_type, "ports": ports}


@frappe.whitelist()
def provision_openas2_instance(
	instance_name: str,
	instance_type: str,
	as2_id: str,
	mdn_enabled: int | str = 1,
	host: str = "localhost",
	description: str | None = None,
) -> dict:
	"""Create one isolated OpenAS2 instance (filesystem + DocType).

	Does not start the Java runtime. Does not modify legacy installs.
	"""
	_require_system_manager()

	instance_name = _validate_instance_name(instance_name)
	as2_id = _validate_as2_id(as2_id)
	instance_type = (instance_type or "").strip()
	if instance_type not in ALLOWED_TYPES:
		frappe.throw(frappe._("Instance Type must be Shipper, Broker, or Carrier."))
	host = (host or "localhost").strip() or "localhost"
	mdn = 1 if cint(mdn_enabled) else 0

	if frappe.db.exists("OpenAS2 Instance", {"instance_name": instance_name}):
		frappe.throw(
			frappe._("Instance Name {0} already exists.").format(frappe.bold(instance_name)),
			frappe.DuplicateEntryError,
		)
	if frappe.db.exists("OpenAS2 Instance", {"as2_id": as2_id}):
		frappe.throw(
			frappe._("AS2 ID {0} already exists.").format(frappe.bold(as2_id)),
			frappe.DuplicateEntryError,
		)

	slug = slugify_instance_name(instance_name)
	# Avoid slug collision with a different instance name
	existing_slug = frappe.db.exists("OpenAS2 Instance", {"instance_slug": slug})
	if existing_slug:
		frappe.throw(
			frappe._("Directory slug {0} is already used by {1}.").format(
				frappe.bold(slug), frappe.bold(existing_slug)
			)
		)

	log_name = _insert_provisioning_log(
		instance_name=instance_name,
		as2_id=as2_id,
		instance_type=instance_type,
		requested_by=frappe.session.user,
		requested_at=now_datetime(),
		result="Failed",
		summary=f"Provisioning started for {instance_name}",
	)

	try:
		_ensure_managed_roots()
		paths = instance_paths(slug)
		if paths["home"].exists() and any(paths["home"].iterdir()):
			frappe.throw(
				frappe._("Instance directory already exists and is not empty: {0}").format(
					paths["home"]
				)
			)

		ports = port_allocator.allocate_ports_for_type(instance_type)
		_create_directory_tree(paths)
		_write_keystore_placeholder(paths["keystore"], paths["home"], as2_id)
		_write_instance_readme(paths["home"], slug=slug, as2_id=as2_id, ports=ports)

		secrets = cg.generate_instance_secrets()
		config_xml = cg.build_config_xml(
			http_port=ports["http_port"],
			https_port=ports["https_port"],
			mdn_http_port=ports["mdn_http_port"],
			mdn_https_port=ports["mdn_https_port"],
			tracking_port=ports["tracking_port"],
			health_port=ports["health_port"],
			mdn_enabled=bool(mdn),
			as2_keystore_password=secrets["as2_keystore_password"],
			ssl_password=secrets["ssl_password"],
			tracking_password=secrets["tracking_password"],
		)
		partner_name = _partner_name_for(instance_type, instance_name)
		x509_alias = _x509_alias_for(slug)
		partnerships_xml = cg.build_minimal_partnerships_xml(
			partner_name=partner_name,
			as2_id=as2_id,
			x509_alias=x509_alias,
		)
		_validate_generated_xml(config_xml, partnerships_xml)

		cg.write_static_support_files(paths["config"], paths["home"])
		config_path = paths["config"] / "config.xml"
		partnerships_path = paths["config"] / "partnerships.xml"
		assert_under_directory(paths["home"], config_path)
		assert_under_directory(paths["home"], partnerships_path)
		config_path.write_text(config_xml, encoding="utf-8")
		partnerships_path.write_text(partnerships_xml, encoding="utf-8")

		# Re-parse from disk
		ET.parse(config_path)
		ET.parse(partnerships_path)

		wsl_home = str(paths["home"])
		win_home = to_windows_path(paths["home"])
		inbox = str(paths["inbox"] / as2_id / "inbox")
		# Create AS2-id inbox folder conventionally used by monitoring
		as2_inbox = paths["inbox"] / as2_id / "inbox"
		assert_under_directory(paths["home"], as2_inbox)
		as2_inbox.mkdir(parents=True, exist_ok=True)

		service_name = f"OpenAS2-{slug}"[:64]
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": instance_name,
				"instance_type": instance_type,
				"as2_id": as2_id,
				"mdn_enabled": mdn,
				"host": host,
				"port": ports["http_port"],
				"protocol": "HTTP",
				"status": "Active",
				"connection_status": "Unknown",
				"lifecycle_status": "Stopped",
				"provision_source": "Manager Provisioned",
				"control_mode": "none",
				"instance_slug": slug,
				"http_port": ports["http_port"],
				"https_port": ports["https_port"],
				"mdn_http_port": ports["mdn_http_port"],
				"mdn_https_port": ports["mdn_https_port"],
				"health_port": ports["health_port"],
				"tracking_port": ports["tracking_port"],
				"openas2_home": wsl_home,
				"windows_home": win_home,
				"inbox_path": inbox,
				"outbox_path": str(paths["outbox"]),
				"service_name": service_name,
				"certificate_status": "Deferred",
				"x509_alias": x509_alias,
				"provisioned_on": now_datetime(),
				"description": description
				or (
					f"Provisioned by OpenAS2 Manager (Phase 1). "
					f"HTTP {ports['http_port']}; HTTPS reserved {ports['https_port']} (disabled). "
					f"Certificate provisioning deferred. Runtime not started."
				),
			}
		)
		doc.insert(ignore_permissions=True)

		# Phase 2: register instance for Runtime Agent (allowlist manifest)
		try:
			from openas2_manager.openas2.runtime_control import write_manager_manifest

			write_manager_manifest(doc)
			doc.db_set("control_mode", "agent", update_modified=False)
		except Exception as manifest_exc:
			# Provisioning still succeeds; Start will rewrite manifest
			frappe.log_error(title="OpenAS2 manifest write", message=str(manifest_exc))

		frappe.db.set_value(
			"OpenAS2 Provisioning Log",
			log_name,
			{
				"result": "Success",
				"instance": doc.name,
				"instance_slug": slug,
				"openas2_home": wsl_home,
				"windows_home": win_home,
				"http_port": ports["http_port"],
				"https_port": ports["https_port"],
				"completed_at": now_datetime(),
				"summary": (
					f"Provisioned {instance_name} ({as2_id}) at {wsl_home}. "
					f"lifecycle=Stopped; cert=Deferred; runtime not started."
				),
			},
			update_modified=True,
		)

		if not getattr(frappe.flags, "in_test", False):
			frappe.db.commit()

		# Never include keystore passwords in the response.
		return {
			"result": "Success",
			"instance": doc.name,
			"instance_name": instance_name,
			"as2_id": as2_id,
			"instance_type": instance_type,
			"lifecycle_status": "Stopped",
			"certificate_status": "Deferred",
			"openas2_home": wsl_home,
			"windows_home": win_home,
			"instances_root_windows": windows_instances_root(),
			"ports": {
				"http": ports["http_port"],
				"https_reserved": ports["https_port"],
				"mdn_http": ports["mdn_http_port"],
				"mdn_https_reserved": ports["mdn_https_port"],
				"tracking": ports["tracking_port"],
				"health_reserved": ports["health_port"],
			},
			"as2_url_http": f"http://{host}:{ports['http_port']}/",
			"service_name": service_name,
			"x509_alias": x509_alias,
			"provisioning_log": log_name,
			"runtime_started": False,
			"message": (
				f"Created isolated OpenAS2 instance '{instance_name}'.\n"
				f"Home: {wsl_home}\n"
				f"HTTP port: {ports['http_port']} (HTTPS reserved {ports['https_port']}, disabled)\n"
				f"Lifecycle: Stopped (not started)\n"
				f"Certificates: Deferred (no PKCS12 generated)\n"
				f"Legacy OpenAS20/A/B installs were not modified."
			),
		}
	except Exception as exc:
		frappe.db.set_value(
			"OpenAS2 Provisioning Log",
			log_name,
			{
				"result": "Failed",
				"completed_at": now_datetime(),
				"error_message": str(exc)[:1000],
				"summary": f"Provisioning failed for {instance_name}",
			},
			update_modified=True,
		)
		if not getattr(frappe.flags, "in_test", False):
			frappe.db.commit()
		raise
